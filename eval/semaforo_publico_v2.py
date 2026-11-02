"""Semáforo público v2: sale del número que ya pasó su medición (cerebro público con la ficha del arranque).

Hipótesis nueva, no un reajuste de la v1 (que no pasó su regla): el nivel se toma de cuánta gente predice el
cerebro público que se va en el gancho y el primer cuarto, contra la curva fija de su duración. Misma vara que
la v1 (docs/decisiones.md, 29-oct): dos periodos que no ha visto, cortes por duración con los 180 días antes del
corte (40 % y 75 %), videos de prueba como de fuera y elegibles, «perdió de más» contra la curva fija.

Uso (desde la raíz del repo):
    python eval/semaforo_publico_v2.py --base BASE.csv --voz VOZ.jsonl --fichas FICHAS.jsonl --salida RUTA.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from semaforo_publico import CALIBRA, MINIMO_DURACION, PRUEBAS  # noqa: E402
from retina.arranque import exceso, wilson  # noqa: E402
from retina.curvas import cargar  # noqa: E402
from retina.predecir import de_fuera  # noqa: E402
from retina.publico import ModeloPublico, entrenar  # noqa: E402


def predicho(m: ModeloPublico, v: dict, voz: dict, fichas: dict) -> tuple[float, np.ndarray]:
    """Gente que el número predice que se va de más en gancho + primer cuarto (puntos), y la curva fija."""
    f = de_fuera(v)
    r = m.predecir(f, tramos=voz.get(v["codigo"]), ficha=fichas.get(v["codigo"]))
    p, base = np.array(r["curva_predicha"]), np.array(r["curva_parecidos"])
    return float(((p[0] - p[10]) - (base[0] - base[10])) * 100), base


def prueba(filas, voz, fichas, corte, fin) -> dict:
    antes = [v for v in filas if v["fecha"] < corte]
    m = ModeloPublico(json.loads(json.dumps(entrenar(antes, voz, {k: f for k, f in fichas.items()}))))
    cortes = {}
    for c in range(5):
        x = [predicho(m, v, voz, fichas)[0] for v in antes if v["cubeta"] == c and v["fecha"] >= corte - CALIBRA
             and v.get("incluir") is True]
        if len(x) >= MINIMO_DURACION:
            cortes[c] = (float(np.percentile(x, 40)), float(np.percentile(x, 75)))
    real, nivel, cub = [], [], []
    for v in filas:
        if not (corte <= v["fecha"] < fin) or v.get("incluir") is not True or v["cubeta"] not in cortes:
            continue
        p, base = predicho(m, v, voz, fichas)
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
         "duraciones_no_medidas": [c for c in range(5) if c not in cortes], "cortes": cortes,
         "base": parte(np.ones(len(real), bool)), "pct_alto": round(100 * float((nivel == "alto").mean()), 1),
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
    ap.add_argument("--fichas", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    voz, fichas = {}, {}
    for l in a.voz.open(encoding="utf-8"):
        d = json.loads(l); voz[d["codigo"]] = d["tramos"]
    for l in a.fichas.open(encoding="utf-8"):
        d = json.loads(l); fichas[d.pop("codigo")] = d
    filas = cargar(a.base)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).parents[1]).stdout.strip()
    r = {"commit": commit, "version": "semaforo-publico-v2", "pruebas": [prueba(filas, voz, fichas, c, f) for c, f in PRUEBAS]}
    r["el_semaforo_se_queda"] = all(all(p["pasa"].values()) for p in r["pruebas"])
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for p in r["pruebas"]:
        print(p["corte"], "n", p["n"], "pct_alto", p["pct_alto"], "base", p["base"]["pct_perdio_de_mas"], p["base"]["ic95"],
              "alto", p["alto"]["pct_perdio_de_mas"], p["alto"]["ic95"], "bajo", p["bajo"]["pct_perdio_de_mas"],
              "no medidas", p["duraciones_no_medidas"], "pasa", p["pasa"])
    print("el semáforo v2 se queda en el modo público:", r["el_semaforo_se_queda"])


if __name__ == "__main__":
    main()
