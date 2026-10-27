"""Curvas de retención: carga, «videos parecidos» y métricas comunes.

Lo usan la línea base (eval/linea_base.py) y el servicio predecir, para que
los dos se midan exactamente igual.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

N_PUNTOS = 41
CORTE_PRUEBA = datetime(2026, 7, 1)
FIN_PRUEBA = datetime(2026, 10, 1)
CUBETAS = [0, 30, 60, 120, 240, 10**6]
MINIMO = 15
VENTANA = timedelta(days=90)


def cubeta(dur: float) -> int:
    return int(np.searchsorted(CUBETAS, dur, side="right") - 1)


def cargar(ruta: Path) -> list[dict]:
    filas = []
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            filas.append({
                "fecha": datetime.strptime(r["fecha_publicacion"][:16], "%Y-%m-%d %H:%M"),
                "dur": float(r["duracion_s"]),
                "codigo": r["codigo_produccion"],
                "talento": r["talento"].strip(),
                "archivo": r.get("archivo_nombre", ""),
                "curva": np.array([float(r[f"c{i:02d}"]) for i in range(N_PUNTOS)]),
            })
    filas.sort(key=lambda x: x["fecha"])
    for x in filas:
        x["cubeta"] = cubeta(x["dur"])
    return filas


def dividir(filas: list[dict]) -> tuple[list[dict], list[dict]]:
    entrenamiento = [x for x in filas if x["fecha"] < CORTE_PRUEBA]
    prueba = [x for x in filas if CORTE_PRUEBA <= x["fecha"] < FIN_PRUEBA]
    assert not {x["codigo"] for x in entrenamiento} & {x["codigo"] for x in prueba}, \
        "Hay producciones repetidas entre entrenamiento y prueba"
    return entrenamiento, prueba


def en_segundo(curva: np.ndarray, dur: float, s: float) -> float:
    return float(np.interp(s / dur, np.linspace(0, 1, N_PUNTOS), curva))


def regla_de_hoy(v: dict, historia: list[dict], entrenamiento: list[dict]) -> tuple[np.ndarray, str]:
    """Promedio de videos parecidos: cubeta + talento en 90 días, luego cubeta en 90 días,
    luego cubeta + talento en entrenamiento, luego cubeta. Nunca el propio video."""
    otros = [h for h in historia if h["codigo"] != v["codigo"] and h["fecha"] < v["fecha"]]
    recientes = [h for h in otros if h["fecha"] >= v["fecha"] - VENTANA and h["cubeta"] == v["cubeta"]]
    opciones = [
        ("cubeta+talento 90 d", [h for h in recientes if v["talento"] and h["talento"] == v["talento"]]),
        ("cubeta 90 d", recientes),
        ("cubeta+talento", [h for h in entrenamiento if h["cubeta"] == v["cubeta"] and h["codigo"] != v["codigo"]
                            and v["talento"] and h["talento"] == v["talento"]]),
        ("cubeta", [h for h in entrenamiento if h["cubeta"] == v["cubeta"] and h["codigo"] != v["codigo"]]),
    ]
    for nombre, grupo in opciones:
        if len(grupo) >= MINIMO or (nombre == "cubeta" and grupo):
            return np.mean([g["curva"] for g in grupo], axis=0), nombre
    return np.mean([h["curva"] for h in entrenamiento], axis=0), "global"


def tramo_exceso(real: np.ndarray, base: np.ndarray) -> int:
    """Tramo donde ESTE video cae más que su base, después del primer 10 % del video.

    Todos pierden gente al inicio; el gancho se deja fuera para no premiar lo obvio.
    """
    exceso = (real[:-1] - real[1:]) - (base[:-1] - base[1:])
    gancho = int(np.ceil(0.10 * (N_PUNTOS - 1)))
    return gancho + int(np.argmax(exceso[gancho:]))


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def intervalo(valores: np.ndarray, f=np.mean, n: int = 2000, semilla: int = 20261026) -> list[float]:
    rng = np.random.default_rng(semilla)
    muestras = [f(valores[rng.integers(0, len(valores), len(valores))]) for _ in range(n)]
    return [round(float(np.percentile(muestras, 2.5)), 3), round(float(np.percentile(muestras, 97.5)), 3)]


def metricas(prueba: list[dict], predichas: list[np.ndarray], bases: list[np.ndarray],
             tramo_predicho: list[int]) -> dict:
    """Las cinco métricas del plan, en puntos porcentuales, con intervalo de 95 %."""
    err = {k: [] for k in ("3s", "15s", "mitad", "final", "curva")}
    real15, pred15, exacto, cerca = [], [], [], []
    for v, p, b, t in zip(prueba, predichas, bases, tramo_predicho):
        c, d = v["curva"], v["dur"]
        err["3s"].append(abs(en_segundo(c, d, 3) - en_segundo(p, d, 3)))
        err["15s"].append(abs(en_segundo(c, d, 15) - en_segundo(p, d, 15)))
        err["mitad"].append(abs(c[20] - p[20]))
        err["final"].append(abs(c[-1] - p[-1]))
        err["curva"].append(float(np.mean(np.abs(c - p))))
        real15.append(en_segundo(c, d, 15)); pred15.append(en_segundo(p, d, 15))
        real_t = tramo_exceso(c, b)
        exacto.append(float(t == real_t)); cerca.append(float(abs(t - real_t) <= 1))
    pp = {k: np.array(v) * 100 for k, v in err.items()}
    a, b_ = np.array(real15), np.array(pred15)
    idx = np.arange(len(a))
    return {
        "n": len(prueba),
        "mae_pp": {k: round(float(v.mean()), 2) for k, v in pp.items()},
        "mae_pp_ic95": {k: intervalo(v) for k, v in pp.items()},
        "spearman_15s": round(spearman(a, b_), 3),
        "spearman_15s_ic95": intervalo(idx, lambda i: spearman(a[i], b_[i]), n=500),
        "tramo_exceso_10pct": {"exacto_pct": round(100 * float(np.mean(exacto)), 1),
                               "mas_menos_1_pct": round(100 * float(np.mean(cerca)), 1)},
    }
