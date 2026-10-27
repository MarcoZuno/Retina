"""Servicio «predecir»: lo que se sabe antes de publicar -> curva de 41 puntos.

v0 (solo metadatos, sin modelos): parte de la regla de hoy («videos
parecidos») y aprende cuánto se aparta cada video de ella con una regresión
ridge sobre lo que ya se sabe antes de publicar: duración, tipo de
producción, talento, hora y día, y las palabras del título. La v1 suma los
vectores de V-JEPA 2 por tramo y los descriptores de Spark.

Uso (medición en los videos de prueba):
    python -m retina.predecir --pares RUTA.csv --salida RUTA.json
"""
from __future__ import annotations

import argparse
import json
import re
import zlib
from pathlib import Path

import numpy as np

from .curvas import N_PUNTOS, cargar, dividir, metricas, regla_de_hoy, tramo_exceso

N_PALABRAS = 1024
VACIAS = set("de la el en y a que los las un una por con para del se su al lo es tu te mp4 reel igtv".split())


def tipo_produccion(codigo: str) -> str:
    m = re.match(r"[A-Z]+", codigo or "")
    return m.group(0) if m else "?"


def palabras_titulo(archivo: str, codigo: str) -> list[str]:
    # El nombre es «AAAA-MM-DD CODIGO TALENTO TIPO EDITOR Título»; se usa todo lo que
    # no es fecha ni código, en minúsculas.
    texto = archivo.replace(codigo, " ").lower()
    texto = re.sub(r"\d{4}-\d{2}-\d{2}", " ", texto)
    return [p for p in re.findall(r"[a-záéíóúñü]{3,}", texto) if p not in VACIAS]


class Rasgos:
    """Convierte un video en un vector; el vocabulario de categorías sale del entrenamiento."""

    def __init__(self, entrenamiento: list[dict]):
        cuenta_tipo, cuenta_tal = {}, {}
        for v in entrenamiento:
            t = tipo_produccion(v["codigo"]); cuenta_tipo[t] = cuenta_tipo.get(t, 0) + 1
            cuenta_tal[v["talento"]] = cuenta_tal.get(v["talento"], 0) + 1
        self.tipos = sorted(t for t, n in cuenta_tipo.items() if n >= 15)
        self.talentos = sorted(t for t, n in cuenta_tal.items() if n >= 15 and t)

    def __call__(self, v: dict, base: np.ndarray) -> np.ndarray:
        d = v["dur"]
        num = [np.log(d), np.log(d) ** 2, v["fecha"].hour / 23,
               np.sin(2 * np.pi * v["fecha"].hour / 24), np.cos(2 * np.pi * v["fecha"].hour / 24)]
        dia = np.eye(7)[v["fecha"].weekday()]
        tipo = np.array([tipo_produccion(v["codigo"]) == t for t in self.tipos], dtype=float)
        tal = np.array([v["talento"] == t for t in self.talentos], dtype=float)
        bolsa = np.zeros(N_PALABRAS)
        for p in palabras_titulo(v["archivo"], v["codigo"]):
            bolsa[zlib.crc32(p.encode()) % N_PALABRAS] = 1.0
        return np.concatenate([[1.0], num, dia, tipo, tal, base, bolsa])


def ajustar_ridge(X: np.ndarray, Y: np.ndarray, lam: float) -> np.ndarray:
    pen = lam * np.eye(X.shape[1]); pen[0, 0] = 0.0  # sin castigo al intercepto
    return np.linalg.solve(X.T @ X + pen, X.T @ Y)


def preparar(filas: list[dict], grupo: list[dict], entrenamiento: list[dict], rasgos: Rasgos):
    bases = [regla_de_hoy(v, filas, entrenamiento)[0] for v in grupo]
    X = np.array([rasgos(v, b) for v, b in zip(grupo, bases)])
    Y = np.array([v["curva"] - b for v, b in zip(grupo, bases)])
    return X, Y, bases


def entrenar(filas: list[dict]) -> dict:
    entrenamiento, prueba = dividir(filas)
    rasgos = Rasgos(entrenamiento)
    # λ se elige con el último 20 % del entrenamiento como validación (también en orden de fecha).
    corte = int(len(entrenamiento) * 0.8)
    ent_a, val = entrenamiento[:corte], entrenamiento[corte:]
    Xa, Ya, _ = preparar(filas, ent_a, ent_a, rasgos)
    Xv, Yv, _ = preparar(filas, val, ent_a, rasgos)
    errores = {}
    for lam in (1, 3, 10, 30, 100, 300, 1000):
        W = ajustar_ridge(Xa, Ya, lam)
        errores[lam] = float(np.mean(np.abs(Xv @ W - Yv)))
    lam = min(errores, key=errores.get)

    X, Y, _ = preparar(filas, entrenamiento, entrenamiento, rasgos)
    W = ajustar_ridge(X, Y, lam)
    Xp, _, bases = preparar(filas, prueba, entrenamiento, rasgos)
    predichas = [np.clip(b + d, 0, 1) for b, d in zip(bases, Xp @ W)]
    tramos = [tramo_exceso(p, b) for p, b in zip(predichas, bases)]
    return {"version": "predecir-v0-metadatos", "lambda": lam,
            "error_validacion_por_lambda": errores,
            "n_rasgos": int(X.shape[1]), **metricas(prueba, predichas, bases, tramos)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pares", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    r = entrenar(cargar(a.pares))
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: r[k] for k in ("lambda", "mae_pp", "spearman_15s", "tramo_exceso_10pct")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
