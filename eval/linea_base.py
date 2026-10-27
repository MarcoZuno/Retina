"""Línea base de Retina: la regla de hoy, medida en los videos de prueba.

La regla («videos parecidos»): promedio de las curvas de los videos de la misma
cubeta de duración y del mismo talento publicados en los 90 días previos; si
no hay al menos 15, solo la cubeta en esos 90 días; si tampoco, la cubeta y el
talento en todo el entrenamiento; si tampoco, la cubeta. Nunca usa el propio
video ni otra publicación de la misma producción.

La regla no predice dónde cae un video más que sus parecidos (su exceso es
cero por construcción); su referencia para esa métrica es adivinar siempre el
tramo más común de la cubeta, aprendido solo en entrenamiento.

Entrada: CSV de pares video-curva (privado, fuera del repo).
Salida: métricas agregadas con intervalo de 95 % (nunca curvas ni títulos).

Uso (desde la raíz del repo):
    python eval/linea_base.py --pares RUTA.csv --salida RUTA.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina.curvas import CUBETAS, cargar, dividir, metricas, regla_de_hoy, tramo_exceso  # noqa: E402


def moda_por_cubeta(entrenamiento: list[dict]) -> dict[int, int]:
    comun: dict[int, list[int]] = {}
    for v in entrenamiento:
        base, _ = regla_de_hoy(v, entrenamiento, entrenamiento)
        comun.setdefault(v["cubeta"], []).append(tramo_exceso(v["curva"], base))
    todos = [t for ts in comun.values() for t in ts]
    global_ = max(set(todos), key=todos.count)
    return {c: (max(set(comun[c]), key=comun[c].count) if c in comun else global_)
            for c in range(len(CUBETAS))}


def medir(filas: list[dict]) -> dict:
    entrenamiento, prueba = dividir(filas)
    moda = moda_por_cubeta(entrenamiento)
    bases, fuentes = [], {}
    for v in prueba:
        base, fuente = regla_de_hoy(v, filas, entrenamiento)
        bases.append(base); fuentes[fuente] = fuentes.get(fuente, 0) + 1
    r = metricas(prueba, bases, bases, [moda[v["cubeta"]] for v in prueba])
    return {"version": "linea-base-v1", "n_entrenamiento": len(entrenamiento),
            "fuente_de_la_regla": fuentes, **r}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pares", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    r = medir(cargar(a.pares))
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: r[k] for k in ("n", "mae_pp", "spearman_15s", "tramo_exceso_10pct",
                                        "fuente_de_la_regla")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
