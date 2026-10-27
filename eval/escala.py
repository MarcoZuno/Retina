"""¿Cuánto ayuda tener más videos? La v0 entrenada con distintas historias.

Siempre se mide en los mismos videos de prueba (jul-sep 2026). Se comparan:
- la regla de hoy y la v0 con la lista congelada (pares previos);
- la regla y la v0 con la base completa, entrenando desde distintos años.
Así se ve si sumar 2020-2024 mejora o si la deriva de los años viejos estorba.

Uso (desde la raíz del repo):
    python eval/escala.py --pares PARES.csv --base BASE.csv --salida RUTA.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina.curvas import cargar, dividir, metricas, regla_de_hoy, tramo_exceso  # noqa: E402
from retina.predecir import Rasgos, ajustar_ridge, preparar  # noqa: E402

RESUMEN = ("n", "mae_pp", "spearman_15s", "tramo_exceso_10pct")


def v0(filas: list[dict], entrenamiento: list[dict], prueba: list[dict]) -> dict:
    """Lo mismo que predecir.entrenar, con la historia y la prueba que se le den."""
    rasgos = Rasgos(entrenamiento)
    corte = int(len(entrenamiento) * 0.8)
    ent_a, val = entrenamiento[:corte], entrenamiento[corte:]
    Xa, Ya, _ = preparar(filas, ent_a, ent_a, rasgos)
    Xv, Yv, _ = preparar(filas, val, ent_a, rasgos)
    errores = {lam: float(np.mean(np.abs(Xv @ ajustar_ridge(Xa, Ya, lam) - Yv))) for lam in (1, 3, 10, 30, 100, 300, 1000)}
    lam = min(errores, key=errores.get)
    X, Y, _ = preparar(filas, entrenamiento, entrenamiento, rasgos)
    W = ajustar_ridge(X, Y, lam)
    Xp, _, bases = preparar(filas, prueba, entrenamiento, rasgos)
    predichas = [np.clip(b + d, 0, 1) for b, d in zip(bases, Xp @ W)]
    m = metricas(prueba, predichas, bases, [tramo_exceso(p, b) for p, b in zip(predichas, bases)])
    return {"n_entrenamiento": len(entrenamiento), "lambda": lam, **{k: m[k] for k in RESUMEN}}


def regla(filas: list[dict], entrenamiento: list[dict], prueba: list[dict]) -> dict:
    bases = [regla_de_hoy(v, filas, entrenamiento)[0] for v in prueba]
    gancho = [tramo_exceso(b, b) for b in bases]  # la regla no distingue videos: su tramo es el de la base
    m = metricas(prueba, bases, bases, gancho)
    return {k: m[k] for k in RESUMEN if k != "tramo_exceso_10pct"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pares", type=Path, required=True)
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()

    A = cargar(a.pares); ent_A, pru_A = dividir(A)
    B = cargar(a.base); ent_B, pru_B = dividir(B)
    congelados = {v["codigo"] for v in pru_A}
    pru_S = [v for v in pru_B if v["codigo"] in congelados]
    r = {"prueba_congelada": len(pru_S), "prueba_completa": len(pru_B),
         "lista_congelada": {"regla": regla(A, ent_A, pru_A), "v0": v0(A, ent_A, pru_A)}}
    print(json.dumps(r, ensure_ascii=False), flush=True)
    for desde in (2025, 2024, 2023, 2022, 2020):
        ent = [v for v in ent_B if v["fecha"] >= datetime(desde, 1, 1)]
        r[f"base_desde_{desde}"] = {"regla_en_congelada": regla(B, ent, pru_S),
                                    "v0_en_congelada": v0(B, ent, pru_S),
                                    "v0_en_completa": v0(B, ent, pru_B)}
        print(desde, json.dumps(r[f"base_desde_{desde}"], ensure_ascii=False), flush=True)
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
