"""¿Retina sirve con un creador que nunca vio?

Prueba de jul-sep 2026, solo videos con talento. Los talentos se reparten en 5
grupos; cada grupo se esconde por completo (entrenamiento e historia de videos
parecidos) y sus videos entran como entraría uno de fuera: sin talento, sin
código y solo con el título publicado. Se comparan:
  A. promedio de videos de su duración (90 días);
  B. Retina de hoy (v0) con esos campos vacíos;
  C. cerebro para cualquier video: duración, reel, hora y día, título y la voz
     del arranque. Nada propio de Badabun.
  D. el cerebro público (retina.publico): C entrenado sin videos no elegibles, sin
     temas fuera de alcance ni graves y sin nombres de talentos, con la curva fija por
     duración que trae el archivo público en lugar de la de los últimos 90 días.
Aparte, en talentos conocidos: v0 contra C más la capa de la casa (talento y
tipo). También la diferencia por video entre B y C (los dos cerebros en los
mismos videos). Reglas escritas antes de correr en docs/decisiones.md (29-oct).

Uso (desde la raíz del repo; la confirmación es --corte 2026-01-01 --fin 2026-07-01):
    python eval/cualquier_video.py --base BASE.csv --voz VOZ.jsonl --salida RUTA.json
"""
from __future__ import annotations

import argparse
import json
import sys
import zlib
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina.curvas import (CORTE_PRUEBA, FIN_PRUEBA, cargar, en_segundo, intervalo, metricas,  # noqa: E402
                           regla_de_hoy, spearman, tramo_exceso)
from retina.curvas import VENTANA  # noqa: E402
from retina.predecir import (LAMBDA_UNIVERSAL, Rasgos, ajustar_ridge, de_fuera, fijos_universales,  # noqa: E402
                             rasgos_universales, tipo_produccion)
from retina.publico import motivo_fuera, nombres, patrones, titulo_publico  # noqa: E402

GRUPOS = 5


def ajustar(Xa, Ya, Xv, Yv) -> tuple[np.ndarray, int]:
    err = {lam: float(np.mean(np.abs(Xv @ ajustar_ridge(Xa, Ya, lam) - Yv))) for lam in (10, 30, 100, 300, 1000, 3000)}
    lam = min(err, key=err.get)
    return ajustar_ridge(np.vstack([Xa, Xv]), np.vstack([Ya, Yv]), lam), lam


class Universal:
    """Los rasgos del cerebro para cualquier video (los mismos de retina.predecir); el título y la
    voz se calculan una vez por video para no repetirlos en cada grupo."""

    def __init__(self, filas: list[dict], voz: dict):
        self.fijo = {id(v): fijos_universales(v["titulo"], voz.get(v["codigo"]), v["dur"]) for v in filas}

    def __call__(self, v: dict, original: dict, base: np.ndarray) -> np.ndarray:
        return rasgos_universales(v, base, self.fijo[id(original)])


def casa(v: dict, rasgos: Rasgos) -> np.ndarray:
    tipo = [tipo_produccion(v["codigo"]) == t for t in rasgos.tipos]
    return np.array(tipo + [v["talento"] == t for t in rasgos.talentos], dtype=float)


def resumen(prueba, pred, bases) -> dict:
    m = metricas(prueba, pred, bases, [tramo_exceso(p, b) for p, b in zip(pred, bases)])
    return {k: m[k] for k in ("n", "mae_pp", "mae_pp_ic95", "spearman_15s", "spearman_15s_ic95")}


def pareja(prueba, p_b, p_c) -> dict:
    """B menos C en los mismos videos: arriba de 0 quiere decir que C se equivoca menos."""
    eb = np.array([np.mean(np.abs(v["curva"] - p)) for v, p in zip(prueba, p_b)]) * 100
    ec = np.array([np.mean(np.abs(v["curva"] - p)) for v, p in zip(prueba, p_c)]) * 100
    real = np.array([en_segundo(v["curva"], v["dur"], 15) for v in prueba])
    b15 = np.array([en_segundo(p, v["dur"], 15) for v, p in zip(prueba, p_b)])
    c15 = np.array([en_segundo(p, v["dur"], 15) for v, p in zip(prueba, p_c)])
    idx = np.arange(len(prueba))
    orden = lambda i: spearman(real[i], c15[i]) - spearman(real[i], b15[i])  # noqa: E731
    return {"curva_b_menos_c_pp": round(float((eb - ec).mean()), 3), "curva_b_menos_c_ic95": intervalo(eb - ec),
            "c_mas_cerca_pct": round(100 * float(np.mean(ec < eb)), 1),
            "orden15_c_menos_b": round(float(orden(idx)), 3), "orden15_c_menos_b_ic95": intervalo(idx, orden, n=500)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--voz", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--corte", default=CORTE_PRUEBA.date().isoformat())
    ap.add_argument("--fin", default=FIN_PRUEBA.date().isoformat())
    a = ap.parse_args()
    corte, fin = datetime.fromisoformat(a.corte), datetime.fromisoformat(a.fin)
    voz = {}
    for l in a.voz.open(encoding="utf-8"):
        d = json.loads(l); voz[d["codigo"]] = d["tramos"]
    filas = cargar(a.base)
    entrenamiento = [v for v in filas if v["fecha"] < corte]
    vistos = {v["codigo"] for v in entrenamiento}
    prueba = [v for v in filas if corte <= v["fecha"] < fin and v["codigo"] not in vistos]
    con_talento = [v for v in prueba if v["talento"]]
    uni = Universal(filas, voz)
    r = {"corte": a.corte, "fin": a.fin, "n_entrenamiento": len(entrenamiento), "n_prueba_con_talento": len(con_talento),
         "con_voz_pct": round(100 * float(np.mean([v["codigo"] in voz for v in con_talento])), 1)}

    # 1. Creador nunca visto: cada grupo de talentos se esconde completo.
    grupo = lambda t: zlib.crc32(t.encode()) % GRUPOS  # noqa: E731
    pred = {"A_promedio_duracion": [], "B_retina_hoy_vacia": [], "C_cualquier_video": [],
            "D_publico_sin_voz": [], "D_publico": []}
    temas, fecha_corte = patrones(), datetime.fromisoformat(a.corte)
    publicable = {v["codigo"] for v in filas if motivo_fuera(v, voz.get(v["codigo"]), temas) is None}
    orden, bases_a, lams = [], [], {"B": [], "C": []}
    for g in range(GRUPOS):
        hist = [v for v in filas if not (v["talento"] and grupo(v["talento"]) == g)]
        ent = [v for v in entrenamiento if not (v["talento"] and grupo(v["talento"]) == g)]
        pru = [v for v in con_talento if grupo(v["talento"]) == g]
        corte = int(len(ent) * 0.8)
        # B: la v0 se entrena como hoy (con talento y código) y recibe el video vacío.
        rasgos = Rasgos(ent)
        base_b = [regla_de_hoy(v, hist, ent)[0] for v in ent]
        Xb = np.array([rasgos(v, b) for v, b in zip(ent, base_b)])
        Yb = np.array([v["curva"] - b for v, b in zip(ent, base_b)])
        Wb, lam_b = ajustar(Xb[:corte], Yb[:corte], Xb[corte:], Yb[corte:])
        # C: todo el entrenamiento entra como de fuera, para que aprenda solo de lo que trae cualquiera.
        fuera = [de_fuera(v) for v in ent]
        base_c = [regla_de_hoy(f, hist, ent)[0] for f in fuera]
        Xc = np.array([uni(f, v, b) for f, v, b in zip(fuera, ent, base_c)])
        Yc = np.array([v["curva"] - b for v, b in zip(ent, base_c)])
        Wc, lam_c = ajustar(Xc[:corte], Yc[:corte], Xc[corte:], Yc[corte:])
        lams["B"].append(lam_b); lams["C"].append(lam_c)
        # D: como se arma el archivo público, pero solo con lo de antes del corte y sin el grupo escondido.
        hist_p = [v for v in hist if v["codigo"] in publicable]
        ent_p = [v for v in ent if v["codigo"] in publicable]
        quitar = nombres(ent)
        limpios = [de_fuera({**v, "titulo": titulo_publico(v["titulo"], quitar)}) for v in ent_p]
        base_d = [regla_de_hoy(f, hist_p, ent_p)[0] for f in limpios]
        Xd = np.array([rasgos_universales(f, b, fijos_universales(f["archivo"], voz.get(v["codigo"]), v["dur"], quitar))
                       for f, v, b in zip(limpios, ent_p, base_d)])
        Wd = ajustar_ridge(Xd, np.array([v["curva"] - b for v, b in zip(ent_p, base_d)]), LAMBDA_UNIVERSAL)
        fija = {}
        for c in range(5):
            rec = [v["curva"] for v in ent_p if v["cubeta"] == c and v["fecha"] > fecha_corte - VENTANA]
            fija[c] = np.mean(rec if len(rec) >= 15 else [v["curva"] for v in ent_p if v["cubeta"] == c], axis=0)
        for v in pru:
            f = de_fuera(v)
            b = regla_de_hoy(f, hist, ent)[0]
            pred["A_promedio_duracion"].append(b)
            pred["B_retina_hoy_vacia"].append(np.clip(b + rasgos(f, b) @ Wb, 0, 1))
            pred["C_cualquier_video"].append(np.clip(b + uni(f, v, b) @ Wc, 0, 1))
            bf = fija[v["cubeta"]]
            pred["D_publico_sin_voz"].append(bf)
            pred["D_publico"].append(np.clip(bf + uni(f, v, bf) @ Wd, 0, 1) if v["codigo"] in voz else bf)
            orden.append(v); bases_a.append(b)
        print(f"grupo {g}: {len(pru)} videos de prueba, {len(ent)} de entrenamiento", flush=True)
    r["nunca_visto"] = {k: resumen(orden, p, bases_a) for k, p in pred.items()}
    r["nunca_visto"]["lambdas"] = lams
    r["nunca_visto"]["pareja_b_contra_c"] = pareja(orden, pred["B_retina_hoy_vacia"], pred["C_cualquier_video"])
    r["nunca_visto"]["pareja_b_contra_d"] = pareja(orden, pred["B_retina_hoy_vacia"], pred["D_publico"])
    r["nunca_visto"]["pareja_promedio_contra_d"] = pareja(orden, pred["D_publico_sin_voz"], pred["D_publico"])

    # 2. Talentos conocidos: lo de la casa encima del cerebro para cualquier video.
    corte = int(len(entrenamiento) * 0.8)
    rasgos = Rasgos(entrenamiento)
    base = [regla_de_hoy(v, filas, entrenamiento)[0] for v in entrenamiento]
    base_p = [regla_de_hoy(v, filas, entrenamiento)[0] for v in con_talento]
    Y = np.array([v["curva"] - b for v, b in zip(entrenamiento, base)])
    X0 = np.array([rasgos(v, b) for v, b in zip(entrenamiento, base)])
    W0, lam0 = ajustar(X0[:corte], Y[:corte], X0[corte:], Y[corte:])
    Xk = np.array([np.concatenate([uni(v, v, b), casa(v, rasgos)]) for v, b in zip(entrenamiento, base)])
    Wk, lamk = ajustar(Xk[:corte], Y[:corte], Xk[corte:], Y[corte:])
    p0 = [np.clip(b + rasgos(v, b) @ W0, 0, 1) for v, b in zip(con_talento, base_p)]
    pk = [np.clip(b + np.concatenate([uni(v, v, b), casa(v, rasgos)]) @ Wk, 0, 1) for v, b in zip(con_talento, base_p)]
    r["conocidos"] = {"v0_hoy": {**resumen(con_talento, p0, base_p), "lambda": lam0},
                      "C_mas_casa": {**resumen(con_talento, pk, base_p), "lambda": lamk}}

    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    for parte in ("nunca_visto", "conocidos"):
        for k, m in r[parte].items():
            if isinstance(m, dict) and "mae_pp" in m:
                print(parte, k, m["n"], m["mae_pp"], m["spearman_15s"], m["spearman_15s_ic95"])
    print("pareja B-C", r["nunca_visto"]["pareja_b_contra_c"])
    print("pareja B-D", r["nunca_visto"]["pareja_b_contra_d"])
    print("pareja promedio-D", r["nunca_visto"]["pareja_promedio_contra_d"])


if __name__ == "__main__":
    main()
