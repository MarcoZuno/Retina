"""¿Lo que se dice al arranque explica cuánta gente se queda?

La curva de Facebook viene en puntos enteros: después del 25 % del video casi
todos los tramos pierden 0 o 1 punto, así que el tramo exacto es ruido de
redondeo. Aquí se mide donde sí hay señal:
1. Curva: la v0 (metadatos) contra la v0 más la voz del primer 25 % del video
   (cuándo arranca la voz, palabras por segundo, pausas, preguntas).
2. Bloque: en cuál de 5 bloques gruesos (gancho, 10-25 %, 25-50 %, 50-75 %,
   75-100 %) se va más gente que en videos parecidos.
Entrena antes de --corte y prueba de --corte a --fin, solo con videos con voz.

Uso (desde la raíz del repo):
    python eval/voz_gancho.py --base BASE.csv --voz VOZ.jsonl --salida RUTA.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina.curvas import CUBETAS, cargar, metricas, regla_de_hoy, tramo_exceso  # noqa: E402
from retina.predecir import Rasgos, ajustar_ridge, caidas  # noqa: E402
from retina.voz import rasgos_voz  # noqa: E402

BLOQUES = [(0, 4), (4, 10), (10, 20), (20, 30), (30, 40)]
INICIO = 10  # tramos del primer 25 %


def voz_inicio(tramos: list, dur: float) -> np.ndarray:
    r = rasgos_voz(tramos, dur)
    primera = min((float(t) for t, _ in tramos), default=dur)
    pal = lambda s: sum(len(x.split()) for t, x in tramos if float(t) < s)  # noqa: E731
    return np.concatenate([r[:INICIO].ravel(), [min(primera, 10) / 10, primera / dur, pal(3) / 10, pal(15) / 40,
                                               float(any("?" in x for t, x in tramos if float(t) < 15))]])


def bloques(caida: np.ndarray) -> np.ndarray:
    return np.array([caida[a:b].sum() for a, b in BLOQUES])


def ajustar(Xa, Ya, Xv, Yv) -> tuple[np.ndarray, int]:
    err = {lam: float(np.mean(np.abs(Xv @ ajustar_ridge(Xa, Ya, lam) - Yv))) for lam in (10, 30, 100, 300, 1000, 3000)}
    lam = min(err, key=err.get)
    return ajustar_ridge(np.vstack([Xa, Xv]), np.vstack([Ya, Yv]), lam), lam


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--voz", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--corte", default="2024-01-01")
    ap.add_argument("--fin", default="2025-01-01")
    a = ap.parse_args()
    corte, fin = datetime.fromisoformat(a.corte), datetime.fromisoformat(a.fin)
    voz = {}
    for l in a.voz.open(encoding="utf-8"):
        d = json.loads(l); voz[d["codigo"]] = d["tramos"]
    filas = cargar(a.base)
    historia = [v for v in filas if v["fecha"] < corte]
    con = [v for v in filas if v["codigo"] in voz]
    ent = [v for v in con if v["fecha"] < corte]
    pru = [v for v in con if corte <= v["fecha"] < fin]
    base = {v["codigo"]: regla_de_hoy(v, filas, historia)[0] for v in ent + pru}
    rasgos = Rasgos(historia)
    meta = {v["codigo"]: rasgos(v, base[v["codigo"]]) for v in ent + pru}
    vz = {v["codigo"]: voz_inicio(voz[v["codigo"]], v["dur"]) for v in ent + pru}
    corte_val = int(len(ent) * 0.8)
    r = {"n_entrenamiento": len(ent), "n_prueba": len(pru)}

    # 1. Curva completa: residuo sobre la regla, con y sin voz.
    Y = lambda g: np.array([v["curva"] - base[v["codigo"]] for v in g])  # noqa: E731
    for nombre, X in (("v0", lambda g: np.array([meta[v["codigo"]] for v in g])),
                      ("v0_mas_voz", lambda g: np.array([np.concatenate([meta[v["codigo"]], vz[v["codigo"]]]) for v in g]))):
        W, lam = ajustar(X(ent[:corte_val]), Y(ent[:corte_val]), X(ent[corte_val:]), Y(ent[corte_val:]))
        bs = [base[v["codigo"]] for v in pru]
        pred = [np.clip(b + d, 0, 1) for b, d in zip(bs, X(pru) @ W)]
        m = metricas(pru, pred, bs, [tramo_exceso(p, b) for p, b in zip(pred, bs)])
        r[f"curva_{nombre}"] = {"lambda": lam, "mae_pp": m["mae_pp"], "mae_pp_ic95": m["mae_pp_ic95"],
                                "spearman_15s": m["spearman_15s"], "spearman_15s_ic95": m["spearman_15s_ic95"]}
    bs = [base[v["codigo"]] for v in pru]
    m = metricas(pru, bs, bs, [4] * len(pru))
    r["curva_regla"] = {"mae_pp": m["mae_pp"], "spearman_15s": m["spearman_15s"]}

    # 2. Bloque grueso con más caída de la cuenta.
    exceso = lambda v: bloques(caidas(v["curva"])) - bloques(caidas(base[v["codigo"]]))  # noqa: E731
    real = np.array([int(np.argmax(exceso(v))) for v in pru])
    t_ent = [int(np.argmax(exceso(v))) for v in ent]
    frec = np.bincount(t_ent, minlength=len(BLOQUES))
    r["bloque_real_por_bloque"] = np.bincount(real, minlength=len(BLOQUES)).tolist()
    r["bloque_moda_pct"] = round(100 * float(np.mean(real == int(np.argmax(frec)))), 1)
    cub = lambda v: np.eye(len(CUBETAS) - 1)[v["cubeta"]]  # noqa: E731
    for nombre, X in (("meta", lambda g: np.array([np.concatenate([meta[v["codigo"]], cub(v)]) for v in g])),
                      ("meta_mas_voz", lambda g: np.array([np.concatenate([meta[v["codigo"]], cub(v), vz[v["codigo"]]]) for v in g]))):
        Ye = lambda g: np.array([exceso(v) for v in g])  # noqa: E731
        W, lam = ajustar(X(ent[:corte_val]), Ye(ent[:corte_val]), X(ent[corte_val:]), Ye(ent[corte_val:]))
        p = X(pru) @ W
        r[f"bloque_{nombre}"] = {"lambda": lam, "acierto_pct": round(100 * float(np.mean(np.argmax(p, 1) == real)), 1),
                                 "corr_exceso_gancho": round(float(np.corrcoef(p[:, 0], Ye(pru)[:, 0])[0, 1]), 3),
                                 "corr_exceso_10_25": round(float(np.corrcoef(p[:, 1], Ye(pru)[:, 1])[0, 1]), 3)}
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
