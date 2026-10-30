"""¿De cuánto suele ser el error del número? De aquí sale el margen que ve la persona.

Esconde creadores completos: reparte los videos del cerebro público en 5 grupos por talento (los que no tienen talento, por
código), entrena con los otros 4 y mide en el que quedó fuera, en el mismo momento que enseña el panel: el segundo 15, o la
mitad del video si dura menos de 30 s. La curva base es la de su duración, calculada también sin ese grupo.

Hay una segunda cuenta más dura, porque el futuro no se parece al pasado: entrena solo con lo anterior a --corte y mide en lo
posterior, también con creadores escondidos. El margen publicado es el mayor de los dos errores medios, redondeado hacia arriba.

A la consola y al archivo solo salen conteos y promedios, nunca un video.

Uso (desde la raíz del repo):
    python eval/margen_numero.py --base BASE.csv --voz VOZ.jsonl --fichas FICHAS.jsonl --salida RUTA.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import zlib
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina.curvas import CUBETAS, cargar, en_segundo  # noqa: E402
from retina.ficha import ficha_a_vector  # noqa: E402
from retina.predecir import LAMBDA_UNIVERSAL, ajustar_ridge, de_fuera, fijos_universales, rasgos_universales  # noqa: E402
from retina.publico import motivo_fuera, nombres, patrones, titulo_publico  # noqa: E402

GRUPOS = 5
N_CUBETAS = len(CUBETAS) - 1


def momento(dur: float) -> float:
    return 15 if dur >= 30 else max(3, round(dur / 2))  # el mismo del panel


def errores(ent: np.ndarray, pru: np.ndarray, X0: np.ndarray, Y: np.ndarray, cub: np.ndarray, dur: np.ndarray, poner_base) -> dict:
    medias = np.array([Y[ent & (cub == c)].mean(axis=0) if (ent & (cub == c)).any() else Y[ent].mean(axis=0) for c in range(N_CUBETAS)])
    B = medias[cub]
    X = poner_base(X0, B)
    W = ajustar_ridge(X[ent], Y[ent] - B[ent], LAMBDA_UNIVERSAL)
    P = np.clip(B[pru] + X[pru] @ W, 0, 1)
    filas = [(en_segundo(Y[i], dur[i], momento(dur[i])), en_segundo(P[j], dur[i], momento(dur[i])), en_segundo(B[i], dur[i], momento(dur[i])))
             for j, i in enumerate(np.where(pru)[0])]
    return {"real": [f[0] for f in filas], "numero": [f[1] for f in filas], "promedio": [f[2] for f in filas]}


def resumen(r: dict) -> dict:
    real, num, prom = (np.array(r[k]) * 100 for k in ("real", "numero", "promedio"))
    e, b, d = np.abs(real - num), np.abs(real - prom), np.abs(num - prom)
    return {"n": len(e), "error_medio": round(float(e.mean()), 2), "error_mediana": round(float(np.median(e)), 2),
            "error_p80": round(float(np.percentile(e, 80)), 2), "error_medio_del_promedio": round(float(b.mean()), 2),
            "se_aparta_del_promedio_p90": round(float(np.percentile(d, 90)), 2)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--voz", type=Path, required=True)
    ap.add_argument("--fichas", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--corte", default="2026-01-01")
    a = ap.parse_args()
    filas, corte = cargar(a.base), datetime.fromisoformat(a.corte)
    voz = {d["codigo"]: d["tramos"] for d in map(json.loads, a.voz.open(encoding="utf-8"))}
    fichas = {}
    for linea in a.fichas.open(encoding="utf-8"):
        d = json.loads(linea); fichas[d.pop("codigo")] = d
    temas = patrones()
    quedan = [v for v in filas if motivo_fuera(v, voz.get(v["codigo"]), temas) is None]
    quitar = nombres(filas)
    afuera = [de_fuera({**v, "titulo": titulo_publico(v.get("titulo", ""), quitar)}) for v in quedan]
    n_base = len(quedan[0]["curva"])
    X0 = np.array([np.concatenate([rasgos_universales(f, np.zeros(n_base), fijos_universales(f["archivo"], voz.get(v["codigo"]), v["dur"], quitar)),
                                   ficha_a_vector(fichas.get(v["codigo"]))]) for f, v in zip(afuera, quedan)])
    inicio = X0.shape[1] - n_base - len(ficha_a_vector(None))  # los rasgos terminan con la curva base y la ficha

    def poner_base(X: np.ndarray, B: np.ndarray) -> np.ndarray:
        Z = X.copy()
        Z[:, inicio:inicio + n_base] = B
        return Z

    grupo = np.array([zlib.crc32((v["talento"] or v["codigo"]).encode()) % GRUPOS for v in quedan])
    cub, dur = np.array([v["cubeta"] for v in quedan]), np.array([v["dur"] for v in quedan])
    Y, fecha = np.array([v["curva"] for v in quedan]), np.array([v["fecha"] for v in quedan])
    salida = {"videos_del_cerebro": len(quedan), "corte": a.corte}
    todos = {"real": [], "numero": [], "promedio": []}
    futuro = {"real": [], "numero": [], "promedio": []}
    for g in range(GRUPOS):
        for caja, ent, pru in ((todos, grupo != g, grupo == g), (futuro, (grupo != g) & (fecha < corte), (grupo == g) & (fecha >= corte))):
            for k, v in errores(ent, pru, X0, Y, cub, dur, poner_base).items():
                caja[k] += v
        print(f"grupo {g + 1} de {GRUPOS}", flush=True)
    salida["creadores_escondidos"], salida["creadores_escondidos_y_despues_del_corte"] = resumen(todos), resumen(futuro)
    salida["margen_personas"] = math.ceil(max(salida["creadores_escondidos"]["error_medio"], salida["creadores_escondidos_y_despues_del_corte"]["error_medio"]))
    a.salida.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(salida, ensure_ascii=False))


if __name__ == "__main__":
    main()
