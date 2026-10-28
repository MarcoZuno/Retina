"""Juez por pares: ¿mirar el video aporta algo que los datos del video no dan?

Spark ve el arranque (gancho y primer cuarto) de dos videos reales del mismo
tipo de producción y dice cuál pierde más gente de la que perdería un video
parecido. Se compara con lo que de verdad pasó (el exceso real de caída del
arranque contra sus parecidos) y con lo que dice el modelo del arranque, que
solo ve datos del video (duración, tipo, hora, título), en los mismos pares.

Los casos salen de eval/casos_api.py: videos ya publicados entre jul y sep
2026, con modelos entrenados solo con lo de antes. Spark no ve el título ni
cifras. Cada par se juzga en los dos órdenes (A/B y B/A) y el veredicto solo
cuenta si el juez elige el mismo video las dos veces: en la prueba de 10 pares
con un solo orden eligió siempre el segundo (sesgo de posición).

El tope de gasto del proyecto manda. Cada par queda en pares.jsonl al
terminarlo, así que la corrida se puede retomar.

Uso (desde la raíz del repo):
    python eval/juez_pares.py --casos CARPETA_CASOS_API [--solo 10] [--hilos 3]
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina import meta_api  # noqa: E402
from retina.esquemas import RAIZ  # noqa: E402

MODELO = "muse-spark-1.3"
SEMILLA = 20261028
DIFERENCIA_MINIMA_PP = 5.0  # solo pares con diferencia clara: los casi empatados no dicen nada
VIDA_ARCHIVO_S = 3600
REUSAR_HASTA_S = 3000       # un archivo subido se reusa mientras le queden 10 min


def instrucciones() -> str:
    return (RAIZ / "skills" / "juez.md").read_text(encoding="utf-8").split("---", 2)[2].strip()


def esquema() -> dict:
    return {"type": "object", "additionalProperties": False,
            "required": ["pierde_mas", "seguridad", "por_que"],
            "properties": {"pierde_mas": {"type": "string", "enum": ["A", "B"]},
                           "seguridad": {"type": "string", "enum": ["alta", "media", "baja"]},
                           "por_que": {"type": "string"}}}


def tipo(codigo: str) -> str:
    return re.match(r"[A-Z]+", codigo).group()


def pares(tabla: list[dict]) -> list[tuple[dict, dict]]:
    por_tipo: dict[str, list[dict]] = {}
    for fila in tabla:
        por_tipo.setdefault(tipo(fila["codigo"]), []).append(fila)
    salida = []
    for filas in por_tipo.values():
        for a, b in itertools.combinations(sorted(filas, key=lambda x: x["codigo"]), 2):
            if abs(a["real_pp"] - b["real_pp"]) >= DIFERENCIA_MINIMA_PP:
                salida.append((a, b))
    return salida


def recortar(carpeta: Path) -> tuple[Path, float]:
    """El arranque son los tramos 0-9 (gancho y primer cuarto)."""
    manifiesto = json.loads((carpeta / "manifiesto.json").read_text(encoding="utf-8"))
    fin = manifiesto["tramos"][9]["fin_s"]
    clip = carpeta / "arranque.mp4"
    if not clip.exists():
        ffmpeg = os.environ.get("FFMPEG", "ffmpeg")
        subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(carpeta / manifiesto["mp4_ligero"]), "-t", f"{fin:.3f}",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-c:a", "aac", str(clip)], check=True)
    return clip, fin


def voz(carpeta: Path, fin_s: float) -> str:
    turnos = json.loads((carpeta / "transcribir.json").read_text(encoding="utf-8")).get("turnos", [])
    lineas = [f"segundo {t['startMs'] / 1000:.1f}: {t['transcript']}" for t in turnos if t["startMs"] / 1000 < fin_s]
    return "\n".join(lineas) or "(sin voz en el arranque)"


class Archivos:
    """Sube cada arranque una vez y lo reusa mientras no caduque."""

    def __init__(self):
        self._ids: dict[str, tuple[str, float]] = {}
        self._candado = threading.Lock()

    def id(self, clip: Path) -> str:
        with self._candado:
            guardado = self._ids.get(str(clip))
            if guardado and time.time() - guardado[1] < REUSAR_HASTA_S:
                return guardado[0]
        nuevo = meta_api.subir_archivo(clip, VIDA_ARCHIVO_S)
        with self._candado:
            self._ids[str(clip)] = (nuevo, time.time())
        return nuevo

    def borrar_todo(self) -> None:
        for file_id, _ in self._ids.values():
            try:
                meta_api.borrar_archivo(file_id)
            except Exception:  # noqa: BLE001 - caducan solos en una hora
                pass


def cuerpo(datos: dict, id_a: str, id_b: str) -> dict:
    return {
        "model": MODELO, "reasoning": {"effort": "low"}, "max_output_tokens": 4000, "store": False,
        "text": {"format": {"type": "json_schema", "name": "juez_v2", "strict": True, "schema": esquema()}},
        "prompt_cache_key": "retina-juez-v2",  # gitleaks:allow
        "input": [
            {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": instrucciones()}]},
            {"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": f"<<<VIDEO_A (dato)\narranque de {datos['fin_a']:.1f} segundos\n"
                                               f"voz:\n{datos['voz_a']}\nVIDEO_A>>>"},
                {"type": "input_file", "file_id": id_a},
                {"type": "input_text", "text": f"<<<VIDEO_B (dato)\narranque de {datos['fin_b']:.1f} segundos\n"
                                               f"voz:\n{datos['voz_b']}\nVIDEO_B>>>"},
                {"type": "input_file", "file_id": id_b},
            ]},
        ],
    }


def juzgar(a: dict, b: dict, casos: Path, archivos: Archivos) -> dict:
    ca, cb = casos / "casos" / a["codigo"], casos / "casos" / b["codigo"]
    (clip_a, fin_a), (clip_b, fin_b) = recortar(ca), recortar(cb)
    datos = {"fin_a": fin_a, "fin_b": fin_b, "voz_a": voz(ca, fin_a), "voz_b": voz(cb, fin_b)}
    respuesta = meta_api.responder("juez", cuerpo(datos, archivos.id(clip_a), archivos.id(clip_b)))
    texto = meta_api.texto_de(respuesta)
    if not texto.strip():
        raise RuntimeError("Spark no devolvió veredicto.")
    v = json.loads(texto)
    codigo = {"A": a["codigo"], "B": b["codigo"]}
    return {"a": a["codigo"], "b": b["codigo"], "tipo": tipo(a["codigo"]),
            "diferencia_pp": round(abs(a["real_pp"] - b["real_pp"]), 1),
            "real": a["codigo"] if a["real_pp"] > b["real_pp"] else b["codigo"],
            "modelo": a["codigo"] if a["predicho_pp"] > b["predicho_pp"] else b["codigo"],
            "juez": codigo[v["pierde_mas"]], "juez_letra": v["pierde_mas"], "seguridad": v["seguridad"],
            "por_que": v["por_que"], "usd": round(meta_api.usd_tokens(MODELO, respuesta.get("usage") or {}), 5)}


def resumen(filas: list[dict]) -> dict:
    por_par: dict[frozenset, list[dict]] = {}
    for f in filas:
        por_par.setdefault(frozenset((f["a"], f["b"])), []).append(f)
    completos = [v for v in por_par.values() if len(v) == 2]
    firmes = [v for v in completos if v[0]["juez"] == v[1]["juez"]]

    def tasa(grupos, quien):
        return round(sum(g[0][quien] == g[0]["real"] for g in grupos) / len(grupos), 3) if grupos else None

    junto = [g for g in firmes if g[0]["juez"] == g[0]["modelo"]]
    distinto = [g for g in firmes if g[0]["juez"] != g[0]["modelo"]]
    return {
        "pares_completos": len(completos),
        "juez_firme": len(firmes), "juez_firme_parte": round(len(firmes) / len(completos), 3) if completos else None,
        "acierto_juez_firme": tasa(firmes, "juez"),
        "acierto_modelo_mismos_pares": tasa(firmes, "modelo"),
        "acierto_modelo_todos": tasa(completos, "modelo"),
        "coinciden": {"pares": len(junto), "acierto": tasa(junto, "juez")},
        "no_coinciden": {"pares": len(distinto), "gana_juez": tasa(distinto, "juez")},
        "juez_elige_segundo": round(sum(f["juez_letra"] == "B" for f in filas) / len(filas), 3) if filas else None,
        "usd": round(sum(f["usd"] for f in filas), 3),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--casos", type=Path, required=True)
    ap.add_argument("--solo", type=int, default=0, help="solo los primeros N pares (prueba)")
    ap.add_argument("--hilos", type=int, default=3)
    a = ap.parse_args()

    tabla = [json.loads(l) for l in (a.casos / "tabla.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    todos = pares(tabla)
    random.Random(SEMILLA).shuffle(todos)
    if a.solo:
        todos = todos[:a.solo]
    salida = a.casos / "juez" / "pares.jsonl"
    salida.parent.mkdir(parents=True, exist_ok=True)
    hechos = [json.loads(l) for l in salida.read_text(encoding="utf-8").splitlines() if l.strip()] if salida.exists() else []
    ya = {(f["a"], f["b"]) for f in hechos}
    ordenes = [o for x, y in todos for o in ((x, y), (y, x))]
    pendientes = [o for o in ordenes if (o[0]["codigo"], o[1]["codigo"]) not in ya]
    print(f"{len(todos)} pares · {len(ordenes)} juicios · {len(hechos)} ya hechos · {len(pendientes)} por hacer")

    archivos, escribir = Archivos(), threading.Lock()
    try:
        with ThreadPoolExecutor(a.hilos) as hilos:
            futuros = {hilos.submit(juzgar, x, y, a.casos, archivos): (x, y) for x, y in pendientes}
            for n, futuro in enumerate(as_completed(futuros), 1):
                try:
                    fila = futuro.result()
                except meta_api.TopeAlcanzado as e:
                    print(f"Me detengo: {e}")
                    for f in futuros:
                        f.cancel()
                    break
                except Exception as e:  # noqa: BLE001 - un par fallido no tumba la corrida
                    p = futuros[futuro]
                    print(f"Falló {p[0]['codigo']} contra {p[1]['codigo']}: {e}")
                    continue
                with escribir, salida.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(fila, ensure_ascii=False) + "\n")
                hechos.append(fila)
                if n % 20 == 0:
                    print(f"{n}/{len(pendientes)} · {json.dumps(resumen(hechos), ensure_ascii=False)}", flush=True)
    finally:
        archivos.borrar_todo()

    r = resumen(hechos)
    (a.casos / "juez" / "resumen.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
