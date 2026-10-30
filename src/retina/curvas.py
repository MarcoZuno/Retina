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
                "titulo": r.get("titulo", ""),
                "reel": float(r.get("tipo_publicacion", "") == "Reels"),
                # Parte de las vistas que vino de elegibilidad; vacío = no se sabe (el cerebro público lo deja fuera).
                "elegibilidad": float(r["participacion_x"]) if r.get("participacion_x") else None,
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
    curva, nombre, _ = grupo_parecido(v, historia, entrenamiento)
    return curva, nombre


class _Indice:
    """Sumas acumuladas por cubeta (y cubeta + talento) ordenadas por fecha.

    Con 30 mil videos, recorrer la historia completa por cada video tarda horas;
    así cada consulta es una búsqueda binaria. Da lo mismo que `_grupo_lento`.
    """

    def __init__(self, historia: list[dict], entrenamiento: list[dict]):
        self.ventanas = {}
        for clave in ("cubeta", "talento"):
            grupos: dict = {}
            for h in historia:
                k = (h["cubeta"],) if clave == "cubeta" else (h["cubeta"], h["talento"])
                grupos.setdefault(k, []).append(h)
            for k, g in grupos.items():
                g = sorted(g, key=lambda x: x["fecha"])
                cs = np.vstack([np.zeros(N_PUNTOS), np.cumsum([x["curva"] for x in g], axis=0)])
                self.ventanas[k] = (np.array([x["fecha"] for x in g], dtype="datetime64[m]"), cs)
        self.totales = {}
        for h in entrenamiento:
            for k in ((h["cubeta"],), (h["cubeta"], h["talento"])):
                s, n = self.totales.get(k, (np.zeros(N_PUNTOS), 0))
                self.totales[k] = (s + h["curva"], n + 1)
        self.por_codigo: dict = {}
        for h in entrenamiento:
            self.por_codigo.setdefault(h["codigo"], []).append(h)
        self.media = np.mean([h["curva"] for h in entrenamiento], axis=0)
        self.n = len(entrenamiento)

    def reciente(self, k: tuple, fecha: datetime) -> tuple[np.ndarray | None, int]:
        if k not in self.ventanas:
            return None, 0
        fechas, cs = self.ventanas[k]
        f = np.datetime64(fecha, "m")
        lo, hi = np.searchsorted(fechas, f - np.timedelta64(VENTANA.days, "D"), "left"), np.searchsorted(fechas, f, "left")
        return ((cs[hi] - cs[lo]) / (hi - lo) if hi > lo else None), int(hi - lo)

    def total(self, k: tuple, v: dict) -> tuple[np.ndarray | None, int]:
        s, n = self.totales.get(k, (np.zeros(N_PUNTOS), 0))
        # Nunca el propio video: se saca su fila de entrenamiento (un video subido para revisar no trae curva).
        for h in self.por_codigo.get(v["codigo"], []):
            if k in ((h["cubeta"],), (h["cubeta"], h["talento"])):
                s, n = s - h["curva"], n - 1
        return (s / n if n else None), n


_INDICES: dict = {}


def grupo_parecido(v: dict, historia: list[dict], entrenamiento: list[dict]) -> tuple[np.ndarray, str, int]:
    """Promedio de videos parecidos: cubeta + talento en 90 días, luego cubeta en 90 días,
    luego cubeta + talento en entrenamiento, luego cubeta. Nunca el propio video."""
    clave = (id(historia), len(historia), id(entrenamiento), len(entrenamiento))
    if clave not in _INDICES:
        _INDICES.clear(); _INDICES[clave] = _Indice(historia, entrenamiento)
    ix = _INDICES[clave]
    c, t = (v["cubeta"],), (v["cubeta"], v["talento"])
    opciones = [("cubeta+talento 90 d", ix.reciente(t, v["fecha"]) if v["talento"] else (None, 0)),
                ("cubeta 90 d", ix.reciente(c, v["fecha"])),
                ("cubeta+talento", ix.total(t, v) if v["talento"] else (None, 0)),
                ("cubeta", ix.total(c, v))]
    for nombre, (curva, n) in opciones:
        if n >= MINIMO or (nombre == "cubeta" and n):
            return curva, nombre, n
    return ix.media, "global", ix.n


def _grupo_lento(v: dict, historia: list[dict], entrenamiento: list[dict]) -> tuple[np.ndarray, str, int]:
    """La definición directa, para comprobar que el índice da lo mismo."""
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
            return np.mean([g["curva"] for g in grupo], axis=0), nombre, len(grupo)
    return np.mean([h["curva"] for h in entrenamiento], axis=0), "global", len(entrenamiento)


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
