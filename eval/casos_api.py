"""Casos explicados para el gate: Retina de punta a punta, con la API, en videos que no vio.

Los modelos (curva y riesgo del arranque) se entrenan solo con lo publicado
antes de --corte. Se eligen --n videos ya publicados entre --corte y --fin,
con archivo, mitad y mitad entre lo que el modelo llama «alto», «medio» y
«bajo», y a cada uno se le corre Retina completo (transcribir, describir,
explicar). Después se compara con lo que de verdad pasó: ¿el arranque perdió
más gente que los videos parecidos?

El tope de gasto del proyecto manda: si se alcanza, se detiene y guarda lo que
lleve. Las carpetas de los casos y la tabla quedan fuera del repo.

Uso (desde la raíz del repo):
    python eval/casos_api.py --base BASE.csv --voz VOZ.jsonl --indice-nas INDICE.json \
        --salida CARPETA [--n 50] [--max-dur 240] [--solo 1]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina import meta_api  # noqa: E402
from retina.arranque import Arranque  # noqa: E402
from retina.curvas import CORTE_PRUEBA, FIN_PRUEBA, cargar  # noqa: E402
from retina.predecir import Modelo, caidas  # noqa: E402
from retina.retina import correr  # noqa: E402
from retina.voz import bloques  # noqa: E402

os.environ.setdefault("RETINA_SOLO_MODELOS_META", "0")  # esta medición es de la fórmula
DESDE = datetime(2025, 1, 1)  # la curva aprende de los años recientes (eval/escala.py)
SEMILLA = 20261028


def preparar_modelos(filas: list[dict], voz: dict, carpeta: Path) -> tuple[Path, Path]:
    modelo, arranque = carpeta / "modelos" / "predecir-hasta-corte.pkl", carpeta / "modelos" / "arranque-hasta-corte.json"
    if not modelo.exists():
        Modelo.entrenar([v for v in filas if DESDE <= v["fecha"] < CORTE_PRUEBA]).guardar(modelo)
    if not arranque.exists():
        Arranque.entrenar(filas, voz, CORTE_PRUEBA).guardar(arranque)
    return modelo, arranque


def elegir(filas: list[dict], indice: dict, modelo: Path, arranque: Path, n: int, max_dur: float) -> list[dict]:
    m, a = Modelo.cargar(modelo), Arranque.cargar(arranque)
    por_nivel = {"alto": [], "medio": [], "bajo": []}
    for v in filas:
        if CORTE_PRUEBA <= v["fecha"] < FIN_PRUEBA and v["archivo"] in indice and v["dur"] <= max_dur:
            base = np.array(m.predecir(v)["curva_parecidos"])
            por_nivel[a.predecir(v, base)["nivel"]].append(v)
    azar = random.Random(SEMILLA)
    cuota = {"alto": n - 2 * (n // 3), "medio": n // 3, "bajo": n // 3}
    elegidos = []
    for nivel, lista in por_nivel.items():
        elegidos += azar.sample(lista, min(cuota[nivel], len(lista)))
    return sorted(elegidos, key=lambda v: v["fecha"])


def real_del_arranque(v: dict, base: list[float]) -> float:
    e = bloques(caidas(v["curva"])) - bloques(caidas(np.array(base)))
    return round(float(e[0] + e[1]) * 100, 1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--voz", type=Path, required=True)
    ap.add_argument("--indice-nas", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--max-dur", type=float, default=240, help="Segundos; los largos cuestan más en describir.")
    ap.add_argument("--solo", type=int, help="Corre solo los primeros N casos (para probar uno antes).")
    a = ap.parse_args()

    filas = cargar(a.base)
    voz = {}
    for l in a.voz.open(encoding="utf-8"):
        d = json.loads(l); voz[d["codigo"]] = d["tramos"]
    indice = json.loads(a.indice_nas.read_text(encoding="utf-8"))
    modelo, arranque = preparar_modelos(filas, voz, a.salida)

    lista = a.salida / "casos.json"
    if not lista.exists():
        lista.write_text(json.dumps([v["codigo"] for v in elegir(filas, indice, modelo, arranque, a.n, a.max_dur)]),
                         encoding="utf-8")
    por_codigo = {v["codigo"]: v for v in filas}
    codigos = json.loads(lista.read_text(encoding="utf-8"))[: a.solo or None]

    tabla = a.salida / "tabla.jsonl"
    hechos = {json.loads(l)["codigo"] for l in tabla.open(encoding="utf-8")} if tabla.exists() else set()
    for i, c in enumerate(codigos, 1):
        if c in hechos:
            continue
        v, t0, gasto0 = por_codigo[c], time.time(), meta_api.gastado_usd()
        try:
            r = correr(Path(indice[v["archivo"]]), modelo, a.salida / "casos" / c, c, v["talento"],
                       v["fecha"].strftime("%Y-%m-%d %H:%M"), v["archivo"], True, arranque, ver_video=False,
                       publicado=True)  # son videos de jul-sep ya publicados
        except meta_api.TopeAlcanzado as e:
            print(f"Me detengo: {e}")
            break
        except Exception as e:  # un video dañado no tira la corrida
            print(f"{i}/{len(codigos)} {c}: falló ({type(e).__name__}: {e})")
            continue
        x, e = r["arranque"], r["explicacion"]
        fila = {"codigo": c, "dur": v["dur"], "nivel": x["nivel"], "predicho_pp": x["exceso_arranque_pp"],
                "real_pp": real_del_arranque(v, r["prediccion"]["curva_parecidos"]),
                "confianza": e["confianza"], "tipo_de_cambio": e["tipo_de_cambio"], "momento_s": e["momento_s"],
                "con_sugerencia": bool(e["que_cambiar"]), "intentos": len(e["licencia"]["intentos"]),
                "usd": round(meta_api.gastado_usd() - gasto0, 4), "segundos": round(time.time() - t0, 1)}
        with tabla.open("a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
        print(f"{i}/{len(codigos)} {c} · {fila['nivel']} · predicho {fila['predicho_pp']:+} pp · real {fila['real_pp']:+} pp"
              f" · USD {fila['usd']:.3f} · {fila['segundos']:.0f} s", flush=True)
    print(f"Gastado en total: USD {meta_api.gastado_usd():.2f} de {meta_api.tope_usd():.0f}")


if __name__ == "__main__":
    main()
