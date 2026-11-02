"""¿El semáforo del cerebro público sirve con videos de fuera? (regla sellada en docs/decisiones.md, 29-oct)

Dos pruebas en periodos que el semáforo no ha visto. En cada una:
1. El cerebro público se arma solo con lo publicado antes del corte (retina.publico.entrenar).
2. Los cortes de «alto» y «medio» se recalculan por duración con lo que predice para los videos de los 180
   días antes del corte (40 % y 75 %), como pasaría al usarlo.
3. Los videos de prueba (solo los elegibles) entran como de fuera, sin talento ni código. «Perdió de más» = su gancho y
   primer cuarto perdieron más gente que la curva fija de su duración, la que ve la persona en la tarjeta.
Cada resultado guarda la huella del commit con el que corrió.

Uso (desde la raíz del repo):
    python eval/semaforo_publico.py --base BASE.csv --voz VOZ.jsonl --salida RUTA.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina.arranque import exceso, wilson  # noqa: E402
from retina.curvas import cargar  # noqa: E402
from retina.predecir import de_fuera  # noqa: E402
from retina.publico import ModeloPublico, entrenar  # noqa: E402

PRUEBAS = [(datetime(2025, 7, 1), datetime(2026, 1, 1)), (datetime(2026, 1, 1), datetime(2026, 7, 1))]
CALIBRA = timedelta(days=180)
MINIMO_DURACION = 50


def predicho(m: ModeloPublico, arr, v: dict) -> tuple[float, np.ndarray]:
    """Lo que predice el modo público para el arranque (gancho + primer cuarto) y la curva fija de su duración."""
    f = de_fuera(v)
    base = np.array(m.predecir(f)["curva_parecidos"])
    return arr.predecir(f, base)["exceso_arranque_pp"], base


def prueba(filas: list[dict], voz: dict, corte: datetime, fin: datetime) -> dict:
    antes = [v for v in filas if v["fecha"] < corte]
    m = ModeloPublico(json.loads(json.dumps(entrenar(antes, voz))))
    arr = m.arranque()
    # Cortes por duración con los 180 días antes del corte (como al usarlo)
    cortes = {}
    for c in range(5):
        x = [predicho(m, arr, v)[0] for v in antes if v["cubeta"] == c and v["fecha"] >= corte - CALIBRA
             and v.get("incluir") is True]
        if len(x) >= MINIMO_DURACION:
            cortes[c] = (float(np.percentile(x, 40)), float(np.percentile(x, 75)))
    real, nivel, cub = [], [], []
    for v in filas:
        if not (corte <= v["fecha"] < fin) or v.get("incluir") is not True or v["cubeta"] not in cortes:
            continue
        p, base = predicho(m, arr, v)
        medio, alto = cortes[v["cubeta"]]
        e = exceso(v, base)
        real.append(float(e[0] + e[1])); cub.append(v["cubeta"])
        nivel.append("alto" if p >= alto else "medio" if p >= medio else "bajo")
    real, nivel, cub = np.array(real), np.array(nivel), np.array(cub)
    perdio = real > 0

    def parte(mask) -> dict:
        n, k = int(mask.sum()), int(perdio[mask].sum())
        return {"n": n, "pct_perdio_de_mas": round(100 * k / n, 1) if n else None, "ic95": wilson(k, n)}

    r = {"corte": corte.date().isoformat(), "fin": fin.date().isoformat(), "n": int(len(real)),
         "duraciones_no_medidas": [c for c in range(5) if c not in cortes],
         "base": parte(np.ones(len(real), bool)),
         "pct_alto": round(100 * float((nivel == "alto").mean()), 1),
         **{k: parte(nivel == k) for k in ("alto", "medio", "bajo")},
         "por_duracion": {str(c): {"n": int((cub == c).sum()), "pct_alto": round(100 * float((nivel[cub == c] == "alto").mean()), 1),
                                   "alto": parte((cub == c) & (nivel == "alto")), "base": parte(cub == c)}
                          for c in sorted(set(cub.tolist()))}}
    b, a = r["base"]["ic95"], r["alto"]["ic95"]
    r["pasa"] = {"pct_alto_entre_15_y_35": 15 <= r["pct_alto"] <= 35,
                 "alto_le_gana_a_la_base": a[0] is not None and b[1] is not None and a[0] > b[1],
                 "bajo_debajo_de_la_base": (r["bajo"]["pct_perdio_de_mas"] or 100) < r["base"]["pct_perdio_de_mas"]}
    return r


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--voz", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    voz = {}
    for l in a.voz.open(encoding="utf-8"):
        d = json.loads(l); voz[d["codigo"]] = d["tramos"]
    filas = cargar(a.base)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).parents[1]).stdout.strip()
    r = {"commit": commit, "pruebas": [prueba(filas, voz, c, f) for c, f in PRUEBAS]}
    r["el_semaforo_se_queda"] = all(all(p["pasa"].values()) for p in r["pruebas"])
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in r["pruebas"]:
        print(p["corte"], "n", p["n"], "pct_alto", p["pct_alto"], "base", p["base"]["pct_perdio_de_mas"], p["base"]["ic95"],
              "alto", p["alto"]["pct_perdio_de_mas"], p["alto"]["ic95"], "bajo", p["bajo"]["pct_perdio_de_mas"],
              "no medidas", p["duraciones_no_medidas"], "pasa", p["pasa"])
    print("el semáforo se queda en el modo público:", r["el_semaforo_se_queda"])


if __name__ == "__main__":
    main()
