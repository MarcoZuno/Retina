"""¿Qué tácticas de arranque retienen mejor y llegan a más gente? (descriptivo, con intervalos)

Con la ficha del arranque (retina.ficha) de cada video y su curva real, solo los elegibles:
  - primer cuarto: retención al terminar el primer cuarto contra sus parecidos (puntos);
  - alcance: alcance contra la mediana de su duración en los 90 días anteriores (veces lo normal).
Por cada rasgo de la ficha (tipo de gancho, si se presenta antes del tema, si el tema llega en la primera frase,
claridad, curiosidad, si pide interacción) da la mediana con intervalo de 95 % por remuestreo. Es una
descripción de lo que pasó, no una causa ni una predicción.

Uso (desde la raíz del repo):
    python eval/tacticas_gancho.py --base BASE.csv --metricas METRICAS.csv --fichas FICHAS.jsonl --salida RUTA.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parents[0] / "src"))
sys.path.insert(0, str(AQUI))
from alcance_privado import PUNTO, alcance_relativo, leer_metricas  # noqa: E402
from retina.curvas import cargar, regla_de_hoy  # noqa: E402

MINIMO = 100


def mediana_ic(x: np.ndarray, semilla: int = 20261029) -> list[float]:
    rng = np.random.default_rng(semilla)
    m = [np.median(rng.choice(x, len(x))) for _ in range(1000)]
    return [round(float(np.median(x)), 2), round(float(np.percentile(m, 2.5)), 2), round(float(np.percentile(m, 97.5)), 2)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--metricas", type=Path, required=True)
    ap.add_argument("--fichas", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    fichas = {}
    for l in a.fichas.open(encoding="utf-8"):
        d = json.loads(l); fichas[d.pop("codigo")] = d
    with a.base.open(encoding="utf-8-sig", newline="") as h:
        post = {r["codigo_produccion"]: r["post_id"] for r in csv.DictReader(h)}
    metricas = leer_metricas(a.metricas)
    filas = cargar(a.base)
    videos = []
    for v in filas:
        m = metricas.get(post.get(v["codigo"], ""))
        if v["codigo"] in fichas and v.get("incluir") is True and m and m["alcance"] and m["alcance"] > 0:
            videos.append({**v, "alcance": m["alcance"], "ficha": fichas[v["codigo"]]})
    alcance_relativo(videos)
    for v in videos:
        base = regla_de_hoy(v, filas, filas)[0]
        v["cuarto_pp"] = float((v["curva"][PUNTO] - base[PUNTO]) * 100)
    videos = [v for v in videos if v["log_alcance"] is not None]
    grupos = {"gancho": lambda f: f["gancho"], "presenta_antes_del_tema": lambda f: f["presenta_antes_del_tema"],
              "tema_en_la_primera_frase": lambda f: f["tema_en_la_primera_frase"], "claridad": lambda f: f["claridad"],
              "curiosidad": lambda f: f["curiosidad"], "promete_algo_visible": lambda f: f["promete_algo_visible"],
              "pide_interaccion": lambda f: f["pide_interaccion"], "emocion": lambda f: f["emocion"]}
    r = {"videos": len(videos), "por_rasgo": {}}
    for nombre, clave in grupos.items():
        tabla = {}
        for valor in sorted({str(clave(v["ficha"])) for v in videos}):
            g = [v for v in videos if str(clave(v["ficha"])) == valor]
            if len(g) < MINIMO:
                continue
            tabla[valor] = {"n": len(g),
                            "primer_cuarto_pp_mediana_ic": mediana_ic(np.array([v["cuarto_pp"] for v in g])),
                            "alcance_veces_lo_normal_ic": [round(float(np.exp(x)), 2) for x in mediana_ic(np.array([v["log_alcance"] for v in g]))]}
        r["por_rasgo"][nombre] = tabla
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print("videos", r["videos"])
    for nombre, tabla in r["por_rasgo"].items():
        print(nombre)
        for valor, x in sorted(tabla.items(), key=lambda kv: -kv[1]["primer_cuarto_pp_mediana_ic"][0]):
            print(f"   {valor:24s} n={x['n']:6d}  primer cuarto {x['primer_cuarto_pp_mediana_ic']}  alcance {x['alcance_veces_lo_normal_ic']}")


if __name__ == "__main__":
    main()
