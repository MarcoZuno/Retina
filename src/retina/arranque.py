"""Riesgo del arranque: ¿el gancho y el primer cuarto pierden más gente que en videos parecidos?

Es la pregunta que el dato sí contesta (la curva de Facebook viene en puntos
enteros; pasado el primer cuarto, la caída por tramo es casi siempre 0 o 1).
Aprende de todos los videos con curva y, cuando hay, con la voz del arranque
(cuándo entra la primera frase, cuánto se dice en 3 y 15 s, pausas, preguntas).

Uso:
    python -m retina.arranque --base BASE.csv --voz VOZ.jsonl --salida MODELO.pkl --eval RUTA.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np

from .curvas import CORTE_PRUEBA, FIN_PRUEBA, cargar, regla_de_hoy
from .predecir import Rasgos, ajustar_ridge, caidas
from .voz import BLOQUES, NOMBRES_BLOQUES, bloques, voz_inicio

N_VOZ = len(voz_inicio([[0.0, "hola"]], 10.0))
LAMBDAS = (10, 30, 100, 300, 1000, 3000)


class Arranque:
    """Dos ridges: con voz (cuando hay transcripción) y solo con metadatos."""

    def __init__(self, rasgos: Rasgos, W: dict, cortes: dict, lam: dict, n: dict):
        self.rasgos, self.W, self.cortes, self.lam, self.n = rasgos, W, cortes, lam, n

    @staticmethod
    def _X(rasgos: Rasgos, v: dict, base: np.ndarray, tramos: list | None) -> np.ndarray:
        cub = np.eye(5)[v["cubeta"]]
        partes = [rasgos(v, base), cub]
        if tramos is not None:
            partes.append(voz_inicio(tramos, v["dur"]))
        return np.concatenate(partes)

    @classmethod
    def entrenar(cls, filas: list[dict], voz: dict, hasta: datetime) -> "Arranque":
        historia = [v for v in filas if v["fecha"] < hasta]
        rasgos = Rasgos(historia)
        base = {v["codigo"]: regla_de_hoy(v, filas, historia)[0] for v in historia}
        W, cortes, lam, n = {}, {}, {}, {}
        for clave in ("con_voz", "sin_voz"):
            g = [v for v in historia if (v["codigo"] in voz) or clave == "sin_voz"]
            X = np.array([cls._X(rasgos, v, base[v["codigo"]], voz.get(v["codigo"]) if clave == "con_voz" else None) for v in g])
            Y = np.array([bloques(caidas(v["curva"])) - bloques(caidas(base[v["codigo"]])) for v in g])
            corte = int(len(g) * 0.8)  # λ con el último 20 %, en orden de fecha
            err = {l: float(np.mean(np.abs(X[corte:] @ ajustar_ridge(X[:corte], Y[:corte], l) - Y[corte:]))) for l in LAMBDAS}
            lam[clave] = min(err, key=err.get)
            W[clave] = ajustar_ridge(X, Y, lam[clave])
            p = X @ W[clave]
            # niveles por percentil del exceso predicho en el arranque (gancho + primer cuarto)
            a = p[:, 0] + p[:, 1]
            cortes[clave] = (float(np.percentile(a, 40)), float(np.percentile(a, 75)))
            n[clave] = len(g)
        return cls(rasgos, W, cortes, lam, n)

    # Medido el 27-oct en jul-sep 2026: la voz no mejora el nivel (las cifras van en la
    # investigación privada). El nivel sale sin voz; la voz va a la explicación.
    USAR_VOZ_EN_NIVEL = False

    def predecir(self, v: dict, base: np.ndarray, tramos: list | None = None) -> dict:
        clave = "con_voz" if tramos and self.USAR_VOZ_EN_NIVEL else "sin_voz"
        p = self._X(self.rasgos, v, base, tramos if clave == "con_voz" else None) @ self.W[clave]
        arranque = float(p[0] + p[1])
        medio, alto = self.cortes[clave]
        nivel = "alto" if arranque >= alto else "medio" if arranque >= medio else "bajo"
        b = bloques(caidas(base))
        peor = int(np.argmax(p[:2]))
        return {
            "nivel": nivel,
            "exceso_arranque_pp": round(arranque * 100, 1),
            "bloque_mas_debil": NOMBRES_BLOQUES[peor],
            "bloques": [{"bloque": NOMBRES_BLOQUES[i], "tramos": list(BLOQUES[i]),
                         "caida_parecidos_pp": round(float(b[i]) * 100, 1),
                         "exceso_predicho_pp": round(float(p[i]) * 100, 1)} for i in range(len(BLOQUES))],
            "uso_voz": clave == "con_voz",
            "entrenado_con": self.n[clave],
        }

    # JSON y no pickle: este modelo sí va al repo público y lo cargan los jueces;
    # un pickle ejecuta código al abrirse. Solo pesos, cortes y vocabulario, sin curvas.
    def guardar(self, ruta: Path) -> None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps({
            "version": "arranque-v1", "tipos": self.rasgos.tipos, "talentos": self.rasgos.talentos,
            "W": {k: w.tolist() for k, w in self.W.items()}, "cortes": self.cortes, "lambda": self.lam, "n": self.n,
        }, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def cargar(ruta: Path) -> "Arranque":
        d = json.loads(ruta.read_text(encoding="utf-8"))
        rasgos = Rasgos([]); rasgos.tipos, rasgos.talentos = d["tipos"], d["talentos"]
        return Arranque(rasgos, {k: np.array(w) for k, w in d["W"].items()},
                        {k: tuple(c) for k, c in d["cortes"].items()}, d["lambda"], d["n"])


def evaluar(filas: list[dict], voz: dict, hasta: datetime, fin: datetime) -> dict:
    """Entrena antes de `hasta` y mide de `hasta` a `fin`, en lenguaje de usuario:
    cuando Retina dice «riesgo alto», ¿qué tan seguido el arranque sí perdió de más?"""
    m = Arranque.entrenar(filas, voz, hasta)
    historia = [v for v in filas if v["fecha"] < hasta]
    prueba = [v for v in filas if hasta <= v["fecha"] < fin]
    r = {"entrena_hasta": hasta.date().isoformat(), "prueba_hasta": fin.date().isoformat(), "lambda": m.lam}
    for clave in ("con_voz", "sin_voz"):
        g = [v for v in prueba if v["codigo"] in voz] if clave == "con_voz" else prueba
        if not g:
            continue
        real, pred, nivel = [], [], []
        for v in g:
            b = regla_de_hoy(v, filas, historia)[0]
            x = m.predecir(v, b, voz.get(v["codigo"]) if clave == "con_voz" else None)
            e = bloques(caidas(v["curva"])) - bloques(caidas(b))
            real.append(float(e[0] + e[1])); pred.append(x["exceso_arranque_pp"] / 100); nivel.append(x["nivel"])
        real, pred, nivel = np.array(real), np.array(pred), np.array(nivel)
        perdio = real > 0
        r[clave] = {
            "n": len(g),
            "corr_exceso_arranque": round(float(np.corrcoef(pred, real)[0, 1]), 3),
            "pct_que_perdio_de_mas": round(100 * float(perdio.mean()), 1),
            "por_nivel": {k: {"n": int((nivel == k).sum()),
                              "pct_perdio_de_mas": round(100 * float(perdio[nivel == k].mean()), 1) if (nivel == k).any() else None,
                              "exceso_real_mediano_pp": round(100 * float(np.median(real[nivel == k])), 1) if (nivel == k).any() else None}
                          for k in ("alto", "medio", "bajo")},
        }
    return r


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--voz", type=Path, required=True)
    ap.add_argument("--salida", type=Path, help="Guarda el modelo entrenado con todo.")
    ap.add_argument("--eval", type=Path, help="Mide en 2024 y en jul-sep 2026 y guarda el JSON.")
    a = ap.parse_args()
    filas = cargar(a.base)
    voz = {}
    for l in a.voz.open(encoding="utf-8"):
        d = json.loads(l); voz[d["codigo"]] = d["tramos"]
    if a.eval:
        r = {"2024": evaluar(filas, voz, datetime(2024, 1, 1), datetime(2025, 1, 1)),
             "jul_sep_2026": evaluar(filas, voz, CORTE_PRUEBA, FIN_PRUEBA)}
        a.eval.parent.mkdir(parents=True, exist_ok=True)
        a.eval.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(r, ensure_ascii=False, indent=1))
    if a.salida:
        Arranque.entrenar(filas, voz, FIN_PRUEBA).guardar(a.salida)
        print(f"modelo guardado en {a.salida}")


if __name__ == "__main__":
    main()
