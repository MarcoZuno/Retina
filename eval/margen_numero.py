"""¿De cuánto suele ser el error del número? De aquí sale el margen que ve la persona.

Esconde creadores completos: reparte los videos del cerebro público en 5 grupos por talento (los que no tienen talento, por
código), entrena con los otros 4 y mide en el que quedó fuera, en el mismo momento que enseña el panel: el segundo 15, o la
mitad del video si dura menos de 30 s.

Entrena y predice con las mismas funciones que producen el cerebro público (`retina.publico.entrenar` y
`ModeloPublico.curva`): la base de cada video de entrenamiento es la regla de hoy, las curvas por duración prefieren los
últimos 90 días del grupo de entrenamiento y cada video escondido se lee como llega uno de fuera, con su título sin nombres de
talentos y con su voz. La curva con la que se compara es la misma «videos como el tuyo» que enseña el panel. Hasta el 1-nov
el margen se medía con un ajuste simplificado (promedios por duración como base, sin la ventana de 90 días); una auditoría
externa lo señaló y desde el 2-nov la cuenta usa el procedimiento publicado.

Hay una segunda cuenta más dura, porque el futuro no se parece al pasado: entrena solo con lo anterior a --corte y mide en lo
posterior, también con creadores escondidos. El margen publicado es el mayor de los dos errores medios, redondeado hacia arriba.

A la consola y al archivo solo salen conteos y promedios, nunca un video.

Uso (desde la raíz del repo):
    python eval/margen_numero.py --base BASE.csv --voz VOZ.jsonl --fichas FICHAS.jsonl --salida RUTA.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import zlib
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina.curvas import cargar, en_segundo  # noqa: E402
from retina.publico import ModeloPublico, entrenar, motivo_fuera, nombres, titulo_publico  # noqa: E402

GRUPOS = 5
MARGEN = 11  # el que enseña el panel: publico.MARGEN_PERSONAS


def momento(dur: float) -> float:
    return 15 if dur >= 30 else max(3, round(dur / 2))  # el mismo del panel


def errores(ent: list[dict], pru: list[dict], voz: dict, fichas: dict, quitar: frozenset) -> dict:
    """Entrena el cerebro público con `ent`, con las mismas funciones que producen modelos/retina-publico.json, y lee cada
    video de `pru` como llega uno de fuera. Devuelve, por video, lo real, el número y la curva de su duración."""
    caja: dict = {"real": [], "numero": [], "promedio": []}
    if not ent or not pru:
        return caja
    modelo = ModeloPublico(entrenar(ent, voz, fichas))
    for v in pru:
        limpio = {**v, "titulo": titulo_publico(v.get("titulo", ""), quitar)}  # sin nombres de talentos, como un título de fuera
        p, b = modelo.curva(limpio, voz.get(v["codigo"]), fichas.get(v["codigo"]))
        m = momento(v["dur"])
        caja["real"].append(en_segundo(np.asarray(v["curva"], dtype=float), v["dur"], m))
        caja["numero"].append(en_segundo(p, v["dur"], m))
        caja["promedio"].append(en_segundo(b, v["dur"], m))
    return caja


def resumen(r: dict) -> dict:
    real, num, prom = (np.array(r[k]) * 100 for k in ("real", "numero", "promedio"))
    e, b, d = np.abs(real - num), np.abs(real - prom), np.abs(num - prom)
    sin_diferencia = d < MARGEN  # lo que el panel dice como «no vemos diferencia»
    return {"n": len(e), "error_medio": round(float(e.mean()), 2), "error_mediana": round(float(np.median(e)), 2),
            "error_p80": round(float(np.percentile(e, 80)), 2), "error_p95": round(float(np.percentile(e, 95)), 2),
            "error_medio_del_promedio": round(float(b.mean()), 2),
            "se_aparta_del_promedio_p90": round(float(np.percentile(d, 90)), 2),
            "dentro_del_margen_pct": round(float((e <= MARGEN).mean() * 100), 1),
            "sin_diferencia_pct": round(float(sin_diferencia.mean() * 100), 1),
            "de_esos_se_aparto_de_verdad_pct": round(float((b[sin_diferencia] >= MARGEN).mean() * 100), 1)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--voz", type=Path, required=True)
    ap.add_argument("--fichas", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--corte", default="2026-01-01")
    a = ap.parse_args()
    filas, corte = cargar(a.base), datetime.fromisoformat(a.corte)
    voz = {d["codigo"]: d["tramos"] for d in map(json.loads, a.voz.open(encoding="utf-8"))}
    fichas = {}
    for linea in a.fichas.open(encoding="utf-8"):
        d = json.loads(linea); fichas[d.pop("codigo")] = d
    quedan = [v for v in filas if motivo_fuera(v) is None]
    quitar = nombres(filas)
    grupo = [zlib.crc32((v["talento"] or v["codigo"]).encode()) % GRUPOS for v in quedan]
    salida = {"videos_del_cerebro": len(quedan), "corte": a.corte, "procedimiento": "retina.publico.entrenar y ModeloPublico.curva por grupo"}
    todos: dict = {"real": [], "numero": [], "promedio": []}
    futuro: dict = {"real": [], "numero": [], "promedio": []}
    for g in range(GRUPOS):
        ent = [v for v, k in zip(quedan, grupo) if k != g]
        pru = [v for v, k in zip(quedan, grupo) if k == g]
        for k, v in errores(ent, pru, voz, fichas, quitar).items():
            todos[k] += v
        for k, v in errores([v for v in ent if v["fecha"] < corte], [v for v in pru if v["fecha"] >= corte], voz, fichas, quitar).items():
            futuro[k] += v
        print(f"grupo {g + 1} de {GRUPOS}", flush=True)
    salida["creadores_escondidos"], salida["creadores_escondidos_y_despues_del_corte"] = resumen(todos), resumen(futuro)
    salida["margen_personas"] = math.ceil(max(salida["creadores_escondidos"]["error_medio"], salida["creadores_escondidos_y_despues_del_corte"]["error_medio"]))
    a.salida.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(salida, ensure_ascii=False))


if __name__ == "__main__":
    main()
