"""¿La voz ubica el tramo donde se va más gente de lo normal?

Como tramo_v1.py, pero con lo que se dice (transcripción con tiempos) en lugar
de lo que se ve. Las transcripciones cubren sobre todo 2020-2024, así que la
prueba es por fecha dentro de esos años: se entrena antes de --corte y se
prueba de --corte a --fin.

Uso (desde la raíz del repo):
    python eval/voz_tramo.py --base BASE.csv --voz VOZ.jsonl --salida RUTA.json \
        [--corte 2024-01-01 --fin 2025-01-01]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina.curvas import CUBETAS, N_PUNTOS, cargar, regla_de_hoy, tramo_exceso  # noqa: E402
from retina.predecir import ajustar_ridge, caidas  # noqa: E402
from retina.voz import rasgos_voz  # noqa: E402

N = N_PUNTOS - 1
GANCHO = int(np.ceil(0.10 * N))


def acierto(pred, real) -> dict:
    p, r = np.array(pred), np.array(real)
    return {"exacto_pct": round(100 * float(np.mean(p == r)), 1),
            "mas_menos_1_pct": round(100 * float(np.mean(np.abs(p - r) <= 1)), 1)}


def X_de(v: dict, voz: np.ndarray | None) -> np.ndarray:
    pos = np.eye(N)
    cub = np.zeros((N, len(CUBETAS) - 1)); cub[:, v["cubeta"]] = 1
    partes = [np.ones((N, 1)), pos, cub]
    if voz is not None:
        # la voz por sí sola y cruzada con la posición gruesa (inicio, medio, final)
        tercio = np.repeat(np.eye(3), [N // 3, N // 3, N - 2 * (N // 3)], axis=0)
        partes += [voz, (voz[:, :, None] * tercio[:, None, :]).reshape(N, -1)]
    return np.hstack(partes)


def medir(filas, voz_por_codigo, corte, fin) -> dict:
    con = [v for v in filas if v["codigo"] in voz_por_codigo]
    ent = [v for v in con if v["fecha"] < corte]
    pru = [v for v in con if corte <= v["fecha"] < fin]
    historia_ent = [v for v in filas if v["fecha"] < corte]
    base = {v["codigo"]: regla_de_hoy(v, filas, historia_ent)[0] for v in ent + pru}
    exceso = lambda v: caidas(v["curva"]) - caidas(base[v["codigo"]])  # noqa: E731
    real = [tramo_exceso(v["curva"], base[v["codigo"]]) for v in pru]
    sonido = {v["codigo"]: rasgos_voz(voz_por_codigo[v["codigo"]], v["dur"]) for v in ent + pru}

    t_ent = [tramo_exceso(v["curva"], base[v["codigo"]]) for v in ent]
    frec = np.bincount(t_ent, minlength=N) / len(t_ent)
    por_cub = {}
    for v, t in zip(ent, t_ent):
        por_cub.setdefault(v["cubeta"], []).append(t)
    moda = {c: max(set(ts), key=ts.count) for c, ts in por_cub.items()}
    top_moda = GANCHO + np.argsort(frec[GANCHO:])[::-1][:3]
    r = {"n_entrenamiento": len(ent), "n_prueba": len(pru),
         "moda": acierto([moda.get(v["cubeta"], int(np.argmax(frec))) for v in pru], real),
         "moda_top3_pct": round(100 * float(np.mean([t in top_moda for t in real])), 1),
         "tramo_real_mas_comun": {int(k): int(n) for k, n in zip(*np.unique(real, return_counts=True)) if n >= len(real) * 0.04}}

    for nombre, usa_voz in (("solo_posicion", False), ("con_voz", True)):
        Xt = np.vstack([X_de(v, sonido[v["codigo"]] if usa_voz else None) for v in ent])
        yt = np.concatenate([exceso(v) for v in ent])
        for lam in (10, 100, 1000):
            W = ajustar_ridge(Xt, yt, lam)
            s = [(X_de(v, sonido[v["codigo"]] if usa_voz else None) @ W)[GANCHO:] for v in pru]
            k = f"{nombre}_lambda_{lam}"
            r[k] = acierto([GANCHO + int(np.argmax(x)) for x in s], real)
            r[k]["top3_pct"] = round(100 * float(np.mean([t in GANCHO + np.argsort(x)[::-1][:3] for x, t in zip(s, real)])), 1)
            r[k]["corr_dentro_del_video"] = round(float(np.nanmean(
                [np.corrcoef(x, exceso(v)[GANCHO:])[0, 1] for x, v in zip(s, pru)])), 3)
    return r


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--voz", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--corte", default="2024-01-01")
    ap.add_argument("--fin", default="2025-01-01")
    a = ap.parse_args()
    voz = {}
    for l in a.voz.open(encoding="utf-8"):
        d = json.loads(l); voz[d["codigo"]] = d["tramos"]
    r = medir(cargar(a.base), voz, datetime.fromisoformat(a.corte), datetime.fromisoformat(a.fin))
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
