"""Predicción contra realidad: lo que dijo Retina de un video ya publicado contra lo que pasó.

Para cada caso de eval/casos_api.py (videos publicados entre jul y sep 2026, con
modelos entrenados solo con lo de antes), compara la curva que predijo Retina y
la regla de hoy (el promedio de sus videos parecidos) contra la curva real de
Facebook: cuánta gente quedaba a los 3 s, a los 15 s, a la mitad y al final, y
el error medio de toda la curva. También si el nivel de riesgo del arranque
coincidió con lo que pasó. No llama a ninguna API.

Uso (desde la raíz del repo):
    python eval/prediccion_vs_real.py --base BASE.csv --casos CARPETA_CASOS_API --salida SALIDA.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina.curvas import cargar, en_segundo  # noqa: E402

PUNTOS = {"3s": lambda c, d: en_segundo(c, d, 3), "15s": lambda c, d: en_segundo(c, d, 15),
          "mitad": lambda c, d: float(c[20]), "final": lambda c, d: float(c[-1])}


def comparar(real: np.ndarray, retina: np.ndarray, regla: np.ndarray, dur: float) -> dict:
    fila = {}
    for nombre, f in PUNTOS.items():
        r, p, b = f(real, dur), f(retina, dur), f(regla, dur)
        fila[nombre] = {"real": round(100 * r, 1), "retina": round(100 * p, 1), "regla": round(100 * b, 1),
                        "error_retina": round(100 * abs(r - p), 1), "error_regla": round(100 * abs(r - b), 1)}
    fila["curva"] = {"error_retina": round(100 * float(np.mean(np.abs(real - retina))), 1),
                     "error_regla": round(100 * float(np.mean(np.abs(real - regla))), 1)}
    return fila


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--casos", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()

    por_codigo = {v["codigo"]: v for v in cargar(a.base)}
    tabla = {json.loads(l)["codigo"]: json.loads(l)
             for l in (a.casos / "tabla.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    casos = []
    for codigo, fila in tabla.items():
        r = json.loads((a.casos / "casos" / codigo / "resultado.json").read_text(encoding="utf-8"))
        v = por_codigo[codigo]
        retina, regla = np.array(r["prediccion"]["curva_predicha"]), np.array(r["prediccion"]["curva_parecidos"])
        casos.append({
            "codigo": codigo, "titulo": v["titulo"], "fecha": v["fecha"].strftime("%Y-%m-%d"), "dur_s": v["dur"],
            "nivel": fila["nivel"], "arranque_real_pp": fila["real_pp"],
            "perdio_de_mas": fila["real_pp"] > 0,
            "explicacion": r["explicacion"].get("por_que", ""), "que_cambiar": r["explicacion"].get("que_cambiar", ""),
            "curvas": {"real": [round(x, 4) for x in v["curva"]], "retina": [round(x, 4) for x in retina],
                       "regla": [round(x, 4) for x in regla]},
            "comparacion": comparar(v["curva"], retina, regla, v["dur"]),
        })

    def media(clave, quien):
        return round(float(np.mean([c["comparacion"][clave][quien] for c in casos])), 1)

    resumen = {k: {"error_retina": media(k, "error_retina"), "error_regla": media(k, "error_regla"),
                   "retina_mas_cerca_pct": round(100 * float(np.mean([c["comparacion"][k]["error_retina"] <
                                                                      c["comparacion"][k]["error_regla"] for c in casos])))}
               for k in (*PUNTOS, "curva")}
    por_nivel = {}
    for n in ("alto", "medio", "bajo"):
        g = [c for c in casos if c["nivel"] == n]
        por_nivel[n] = {"videos": len(g), "perdieron_de_mas": sum(c["perdio_de_mas"] for c in g)}
    a.salida.write_text(json.dumps({"n": len(casos), "resumen": resumen, "por_nivel": por_nivel, "casos": casos},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"n": len(casos), "resumen": resumen, "por_nivel": por_nivel}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
