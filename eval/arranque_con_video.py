"""¿Lo que ya se mide del video en local mejora el nivel de riesgo del arranque? (prueba gratis)

Regla escrita antes de correr: docs/decisiones.md, 28-oct-2026 (noche).

Base: arranque-v2 sin voz, entrenado antes del 1-jul-2026. Ajuste: un ridge sobre lo que el
modelo base no explicó (el residuo), con rasgos del arranque que ya existen en local:
- V-JEPA 2: promedio de los vectores de los tramos 0-9, reducido con PCA (ajustada solo con
  entrenamiento);
- ritmo visual: distancia coseno entre tramos seguidos 0-9 (cuánto cambia la imagen);
- audio por tramo 0-9 (4 medidas por tramo).
Prueba: jul-sep 2026 con vectores, sin los 50 casos del gate. Comparación principal: correlación
entre el exceso predicho y el real del arranque, con y sin ajuste, en los mismos videos, con
remuestreo de 2,000. Sin API.

Uso (desde la raíz del repo):
    python eval/arranque_con_video.py --base BASE.csv --voz VOZ.jsonl --embebidos CARPETA \
        --excluir TABLA_GATE.jsonl --salida RUTA.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina.arranque import LAMBDAS, Arranque, exceso  # noqa: E402
from retina.curvas import CORTE_PRUEBA, FIN_PRUEBA, cargar, regla_de_hoy  # noqa: E402
from retina.predecir import ajustar_ridge  # noqa: E402

TRAMOS = range(10)
PCA_DIMS = (8, 16, 32)


def rasgos_video(carpeta: Path, codigo: str) -> dict | None:
    v, a = carpeta / f"{codigo}.npy", carpeta / f"{codigo}.audio.npy"
    if not v.exists():
        return None
    e = np.load(v).astype(np.float32)[list(TRAMOS)]
    n = e / (np.linalg.norm(e, axis=1, keepdims=True) + 1e-8)
    ritmo = 1 - np.sum(n[1:] * n[:-1], axis=1)
    audio = np.load(a).astype(np.float32)[list(TRAMOS)].ravel() if a.exists() else None
    return {"media": e.mean(axis=0), "ritmo": np.concatenate([ritmo, [ritmo.mean(), ritmo.max()]]), "audio": audio}


def correlacion(p: np.ndarray, r: np.ndarray) -> float:
    return float(np.corrcoef(p, r)[0, 1])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--voz", type=Path, required=True)
    ap.add_argument("--embebidos", type=Path, required=True)
    ap.add_argument("--excluir", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--hasta", default=None, help="Fecha de corte AAAA-MM-DD (por omisión, 1-jul-2026).")
    ap.add_argument("--fin", default=None, help="Fin de la prueba AAAA-MM-DD (por omisión, 1-oct-2026).")
    ap.add_argument("--variante", default=None, help="Variante fijada antes de correr (confirmación).")
    a = ap.parse_args()

    filas = cargar(a.base)
    voz = {}
    for l in a.voz.open(encoding="utf-8"):
        d = json.loads(l); voz[d["codigo"]] = d["tramos"]
    excluir = {json.loads(l)["codigo"] for l in a.excluir.read_text(encoding="utf-8").splitlines() if l.strip()}
    from datetime import datetime
    hasta = datetime.fromisoformat(a.hasta) if a.hasta else CORTE_PRUEBA
    fin = datetime.fromisoformat(a.fin) if a.fin else FIN_PRUEBA
    m = Arranque.entrenar(filas, voz, hasta)
    historia = [v for v in filas if v["fecha"] < hasta]

    def fila(v):
        rv = rasgos_video(a.embebidos, v["codigo"])
        if rv is None or rv["audio"] is None:
            return None
        b = regla_de_hoy(v, filas, historia)[0]
        e = exceso(v, b) - m.correccion(v)
        return {"v": v, "rv": rv, "base": m.predecir(v, b)["exceso_arranque_pp"] / 100, "real": float(e[0] + e[1])}

    ent = [x for x in (fila(v) for v in historia) if x]
    pru = [x for x in (fila(v) for v in filas if hasta <= v["fecha"] < fin and v["codigo"] not in excluir) if x]
    ent.sort(key=lambda x: x["v"]["fecha"])
    print(f"entrenamiento con vectores: {len(ent)} · prueba: {len(pru)}")

    def matriz(xs, pca, dims, mu, sd, partes):
        bloques = []
        if "vjepa" in partes:
            bloques.append((np.array([x["rv"]["media"] for x in xs]) - pca[0]) @ pca[1][:dims].T)
        if "ritmo" in partes:
            bloques.append(np.array([x["rv"]["ritmo"] for x in xs]))
        if "audio" in partes:
            bloques.append(np.array([x["rv"]["audio"] for x in xs]))
        X = np.hstack(bloques)
        if mu is None:
            mu, sd = X.mean(axis=0), X.std(axis=0) + 1e-6
        return np.hstack([np.ones((len(xs), 1)), (X - mu) / sd]), mu, sd

    M = np.array([x["rv"]["media"] for x in ent])
    centro = M.mean(axis=0)
    _, _, vt = np.linalg.svd(M - centro, full_matrices=False)
    pca = (centro, vt)
    yb_ent = np.array([x["real"] - x["base"] for x in ent])
    base_p, real_p = np.array([x["base"] for x in pru]), np.array([x["real"] for x in pru])

    variantes = {}
    for partes in (("vjepa",), ("ritmo",), ("audio",), ("vjepa", "ritmo", "audio")):
        for dims in (PCA_DIMS if "vjepa" in partes else (0,)):
            X, mu, sd = matriz(ent, pca, dims, None, None, partes)
            corte = int(len(ent) * 0.8)
            err = {l: float(np.mean(np.abs(X[corte:] @ ajustar_ridge(X[:corte], yb_ent[:corte], l) - yb_ent[corte:])))
                   for l in LAMBDAS}
            lam = min(err, key=err.get)
            W = ajustar_ridge(X, yb_ent, lam)
            Xp, _, _ = matriz(pru, pca, dims, mu, sd, partes)
            nuevo = base_p + Xp @ W
            variantes["+".join(partes) + (f"-pca{dims}" if dims else "")] = {
                "lambda": lam, "error_validacion": round(err[lam], 5), "pred": nuevo}

    # La variante principal se elige con validación de entrenamiento, nunca con la prueba.
    principal = a.variante or min(variantes, key=lambda k: variantes[k]["error_validacion"])
    azar = np.random.default_rng(20261028)
    idx = np.arange(len(pru))
    difs = []
    for _ in range(2000):
        i = azar.choice(idx, len(idx))
        difs.append(correlacion(variantes[principal]["pred"][i], real_p[i]) - correlacion(base_p[i], real_p[i]))
    lo, hi = np.percentile(difs, [2.5, 97.5])
    r = {
        "regla": "docs/decisiones.md 28-oct-2026 (noche)", "entrena_hasta": hasta.date().isoformat(),
        "prueba_hasta": fin.date().isoformat(), "variante_fijada": bool(a.variante), "n_entrenamiento": len(ent), "n_prueba": len(pru),
        "corr_base": round(correlacion(base_p, real_p), 3),
        "principal": principal,
        "corr_principal": round(correlacion(variantes[principal]["pred"], real_p), 3),
        "mejora_ic95": [round(float(lo), 3), round(float(hi), 3)],
        "gana": bool(lo > 0),
        "todas": {k: {"lambda": v["lambda"], "error_validacion": v["error_validacion"],
                      "corr_prueba": round(correlacion(v["pred"], real_p), 3)} for k, v in variantes.items()},
    }
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
