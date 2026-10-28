"""¿Los videos que fallan una recomendación de Meta perdieron más gente al inicio? (50 casos, sin API)

Para cada regla de reglas/recomendaciones-meta-v1.json compara el exceso real de caída del
inicio (contra sus parecidos) entre los casos que la cumplen y los que no, con un intervalo
del 95 % por remuestreo. Con 50 casos es una pista, no una prueba: sirve para decidir si la
revisión se presenta como «esto te está costando gente» o como «Meta recomienda esto».

Uso (desde la raíz del repo):
    python eval/revision_meta_casos.py --casos CARPETA_CASOS_API --salida RUTA.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina.revision_meta import revisar  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--casos", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    tabla = {json.loads(l)["codigo"]: json.loads(l)
             for l in (a.casos / "tabla.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    filas = {}
    for c, f in tabla.items():
        for r in revisar(a.casos / "casos" / c):
            if r["cumple"] is not None:
                filas.setdefault(r["id"], []).append((r["cumple"], f["real_pp"]))
    azar = np.random.default_rng(20261028)
    salida = {}
    for rid, xs in filas.items():
        si = np.array([x for c, x in xs if c]); no = np.array([x for c, x in xs if not c])
        r = {"cumplen": len(si), "no_cumplen": len(no)}
        if len(si) >= 5 and len(no) >= 5:
            difs = [azar.choice(no, len(no)).mean() - azar.choice(si, len(si)).mean() for _ in range(2000)]
            r.update(exceso_cumplen_pp=round(float(si.mean()), 1), exceso_no_cumplen_pp=round(float(no.mean()), 1),
                     diferencia_ic95_pp=[round(float(np.percentile(difs, 2.5)), 1), round(float(np.percentile(difs, 97.5)), 1)])
        salida[rid] = r
    a.salida.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(salida, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
