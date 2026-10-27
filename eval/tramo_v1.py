"""¿Dónde se va más gente de lo normal? Comparación de formas de ubicar el tramo.

Mide, en los mismos videos de prueba que ya tienen vector de V-JEPA 2:
- moda: siempre el tramo más común de la cubeta (aprendido en entrenamiento);
- directo: ridge por tramo que predice el exceso de caída contra videos
  parecidos con lo que se ve (V-JEPA 2) y dónde está, y toma el mayor;
- directo + moda: lo mismo con la posición más común como desempate.
Solo se buscan tramos después del primer 10 % del video, como en la métrica.

Uso (desde la raíz del repo):
    python eval/tramo_v1.py --pares RUTA.csv --vectores CARPETA --salida RUTA.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina.curvas import N_PUNTOS, cargar, dividir, regla_de_hoy, tramo_exceso  # noqa: E402
from retina.predecir import K_PCA, ajustar_ridge, caidas, cargar_audio, rasgos_tramo  # noqa: E402

GANCHO = int(np.ceil(0.10 * (N_PUNTOS - 1)))


def con_vector(carpeta: Path, grupo: list[dict]) -> list[dict]:
    fuera = []
    for v in grupo:
        p = carpeta / f"{v['codigo']}.npy"
        try:
            if p.exists() and np.load(p).shape == (N_PUNTOS - 1, 1024):
                fuera.append(v)
        except (ValueError, OSError):
            pass
    return fuera


def acierto(pred: list[int], real: list[int]) -> dict:
    p, r = np.array(pred), np.array(real)
    return {"exacto_pct": round(100 * float(np.mean(p == r)), 1),
            "mas_menos_1_pct": round(100 * float(np.mean(np.abs(p - r) <= 1)), 1)}


def medir(filas: list[dict], carpeta: Path, con_audio: bool = False) -> dict:
    entrenamiento, prueba = dividir(filas)
    ent, pru = con_vector(carpeta, entrenamiento), con_vector(carpeta, prueba)
    if con_audio:  # se comparan solo videos que tengan los dos, para medir parejo
        ent = [v for v in ent if (carpeta / f"{v['codigo']}.audio.npy").exists()]
        pru = [v for v in pru if (carpeta / f"{v['codigo']}.audio.npy").exists()]
    base = {v["codigo"]: regla_de_hoy(v, filas, entrenamiento)[0] for v in ent + pru}
    emb = {v["codigo"]: np.load(carpeta / f"{v['codigo']}.npy") for v in ent + pru}

    muestra = np.vstack([emb[v["codigo"]] for v in ent]).astype(np.float32)
    media = muestra.mean(axis=0)
    proy = np.linalg.svd(muestra[::7] - media, full_matrices=False)[2][:K_PCA].T

    sonido = {v["codigo"]: cargar_audio(carpeta, v["codigo"]) for v in ent + pru} if con_audio else {}

    def X(v):
        return np.hstack([np.ones((N_PUNTOS - 1, 1)),
                          rasgos_tramo(emb[v["codigo"]], proy, media, v["cubeta"], sonido.get(v["codigo"]))])

    exceso = lambda v: caidas(v["curva"]) - caidas(base[v["codigo"]])  # noqa: E731
    real = [tramo_exceso(v["curva"], base[v["codigo"]]) for v in pru]

    tramos_ent = {}
    for v in ent:
        tramos_ent.setdefault(v["cubeta"], []).append(tramo_exceso(v["curva"], base[v["codigo"]]))
    todos = [t for ts in tramos_ent.values() for t in ts]
    frec = np.bincount(todos, minlength=N_PUNTOS - 1) / len(todos)
    moda = {c: max(set(ts), key=ts.count) for c, ts in tramos_ent.items()}
    r = {"n_entrenamiento": len(ent), "n_prueba": len(pru),
         "moda": acierto([moda.get(v["cubeta"], int(np.argmax(frec))) for v in pru], real)}

    Xt = np.vstack([X(v) for v in ent]); yt = np.concatenate([exceso(v) for v in ent])
    for lam in (10, 100, 1000, 10000):
        W = ajustar_ridge(Xt, yt, lam)
        pred = [GANCHO + int(np.argmax((X(v) @ W)[GANCHO:])) for v in pru]
        r[f"directo_lambda_{lam}"] = acierto(pred, real)
        # con desempate por lo común: suma una fracción de la frecuencia de cada posición
        escala = float(np.std(Xt @ W))
        pred2 = [GANCHO + int(np.argmax((X(v) @ W + escala * frec)[GANCHO:])) for v in pru]
        r[f"directo_mas_moda_lambda_{lam}"] = acierto(pred2, real)
    return r


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pares", type=Path, required=True)
    ap.add_argument("--vectores", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--audio", action="store_true", help="Suma volumen y silencios por tramo.")
    a = ap.parse_args()
    r = medir(cargar(a.pares), a.vectores, a.audio)
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
