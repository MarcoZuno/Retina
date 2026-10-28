"""Riesgo del arranque: ¿el gancho y el primer cuarto pierden más gente que en videos parecidos?

Es la pregunta que el dato sí contesta (la curva de Facebook viene en puntos
enteros; pasado el primer cuarto, la caída por tramo es casi siempre 0 o 1).
Aprende de todos los videos con curva y, cuando hay, con la voz del arranque
(cuándo entra la primera frase, cuánto se dice en 3 y 15 s, pausas, preguntas).

«Perder de más» se mide contra la regla de hoy corregida por tipo de producción:
la regla más el exceso medio de su tipo en los 180 días antes del corte. Sin esa
corrección, el «alto» acertaba sobre todo por ser de un tipo que casi siempre
pierde de más (auditoría del 28-oct, eval/arranque_privado.py).

Uso:
    python -m retina.arranque --base BASE.csv --voz VOZ.jsonl --salida MODELO.json \
        [--publico MODELO-PUBLICO.json] [--eval RUTA.json]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from .curvas import CORTE_PRUEBA, FIN_PRUEBA, cargar, regla_de_hoy
from .predecir import Rasgos, ajustar_ridge, caidas, tipo_produccion
from .voz import BLOQUES, NOMBRES_BLOQUES, bloques, voz_inicio

N_VOZ = len(voz_inicio([[0.0, "hola"]], 10.0))
LAMBDAS = (10, 30, 100, 300, 1000, 3000)
VENTANA_TIPO = timedelta(days=180)


def exceso(v: dict, base: np.ndarray) -> np.ndarray:
    return bloques(caidas(v["curva"])) - bloques(caidas(base))


def delta_por_tipo(historia: list[dict], base: dict, hasta: datetime) -> dict[str, np.ndarray]:
    """Exceso medio de cada tipo de producción (5 bloques) en los 180 días antes de `hasta`."""
    grupos: dict[str, list] = {}
    for v in historia:
        if v["fecha"] >= hasta - VENTANA_TIPO:
            grupos.setdefault(tipo_produccion(v["codigo"]), []).append(exceso(v, base[v["codigo"]]))
    return {t: np.mean(x, axis=0) for t, x in grupos.items() if len(x) >= 15}


class Arranque:
    """Dos ridges: con voz (cuando hay transcripción) y solo con metadatos."""

    def __init__(self, rasgos: Rasgos, W: dict, cortes: dict, lam: dict, n: dict, delta: dict | None = None):
        self.rasgos, self.W, self.cortes, self.lam, self.n = rasgos, W, cortes, lam, n
        self.delta = delta or {}

    def correccion(self, v: dict) -> np.ndarray:
        return self.delta.get(tipo_produccion(v["codigo"]), np.zeros(len(BLOQUES)))

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
        delta = delta_por_tipo(historia, base, hasta)
        cero = np.zeros(len(BLOQUES))
        W, cortes, lam, n = {}, {}, {}, {}
        for clave in ("con_voz", "sin_voz"):
            g = [v for v in historia if (v["codigo"] in voz) or clave == "sin_voz"]
            X = np.array([cls._X(rasgos, v, base[v["codigo"]], voz.get(v["codigo"]) if clave == "con_voz" else None) for v in g])
            Y = np.array([exceso(v, base[v["codigo"]]) - delta.get(tipo_produccion(v["codigo"]), cero) for v in g])
            corte = int(len(g) * 0.8)  # λ con el último 20 %, en orden de fecha
            err = {l: float(np.mean(np.abs(X[corte:] @ ajustar_ridge(X[:corte], Y[:corte], l) - Y[corte:]))) for l in LAMBDAS}
            lam[clave] = min(err, key=err.get)
            W[clave] = ajustar_ridge(X, Y, lam[clave])
            p = X @ W[clave]
            # niveles por percentil del exceso predicho en el arranque (gancho + primer cuarto)
            a = p[:, 0] + p[:, 1]
            cortes[clave] = (float(np.percentile(a, 40)), float(np.percentile(a, 75)))
            n[clave] = len(g)
        return cls(rasgos, W, cortes, lam, n, delta)

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
        # Sin «bloque más débil» ni exceso por bloque: elegir el bloque no le gana a decir
        # siempre el más común (medido el 27-oct). Los bloques van solo como contexto.
        return {
            "nivel": nivel,
            "exceso_arranque_pp": round(arranque * 100, 1),
            "bloques": [{"bloque": NOMBRES_BLOQUES[i], "tramos": list(BLOQUES[i]),
                         "caida_parecidos_pp": round(float(b[i]) * 100, 1)} for i in range(len(BLOQUES))],
            "uso_voz": clave == "con_voz",
            "entrenado_con": self.n[clave],
            "comparado_con_su_tipo": bool(self.delta),
        }

    # JSON y no pickle: este modelo sí va al repo público y lo cargan los jueces;
    # un pickle ejecuta código al abrirse. Solo pesos, cortes y vocabulario, sin curvas.
    # `publico=True` quita los nombres de talento y sus pesos (dicen cómo rinde cada persona):
    # es la versión que puede ir al repo. Sin talento, el modelo pierde poco (sale en la evaluación).
    def guardar(self, ruta: Path, publico: bool = False) -> None:
        W, talentos = self.W, self.rasgos.talentos
        if publico:
            ini = 1 + 5 + 7 + len(self.rasgos.tipos)  # [1, números, día, tipo, talento, …] en Rasgos
            W = {k: np.delete(w, range(ini, ini + len(talentos)), axis=0) for k, w in W.items()}
            talentos = []
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps({
            "version": "arranque-v2", "publico": publico, "tipos": self.rasgos.tipos, "talentos": talentos,
            "W": {k: w.tolist() for k, w in W.items()}, "cortes": self.cortes, "lambda": self.lam, "n": self.n,
            "delta_por_tipo": {t: d.tolist() for t, d in self.delta.items()},
        }, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def cargar(ruta: Path) -> "Arranque":
        d = json.loads(ruta.read_text(encoding="utf-8"))
        rasgos = Rasgos([]); rasgos.tipos, rasgos.talentos = d["tipos"], d["talentos"]
        return Arranque(rasgos, {k: np.array(w) for k, w in d["W"].items()},
                        {k: tuple(c) for k, c in d["cortes"].items()}, d["lambda"], d["n"],
                        {t: np.array(x) for t, x in d.get("delta_por_tipo", {}).items()})


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    """Intervalo de Wilson al 95 % para una proporción, en %."""
    if not n:
        return [None, None]
    q = k / n
    c = (q + z * z / (2 * n)) / (1 + z * z / n)
    m = z * ((q * (1 - q) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)
    return [round(100 * (c - m), 1), round(100 * (c + m), 1)]


def evaluar(filas: list[dict], voz: dict, hasta: datetime, fin: datetime) -> dict:
    """Entrena antes de `hasta` y mide de `hasta` a `fin`, en lenguaje de usuario:
    cuando Retina dice «riesgo alto», ¿qué tan seguido el arranque sí perdió más gente
    que videos parecidos de su mismo tipo? Mide también la versión pública (sin talentos)."""
    import tempfile
    m = Arranque.entrenar(filas, voz, hasta)
    with tempfile.TemporaryDirectory() as d:
        m.guardar(Path(d) / "publico.json", publico=True)
        publico = Arranque.cargar(Path(d) / "publico.json")
    historia = [v for v in filas if v["fecha"] < hasta]
    prueba = [v for v in filas if hasta <= v["fecha"] < fin]
    r = {"entrena_hasta": hasta.date().isoformat(), "prueba_hasta": fin.date().isoformat(), "lambda": m.lam,
         "vara": "regla de hoy corregida por tipo de producción"}
    for nombre, modelo in (("sin_voz", m), ("publico_sin_talentos", publico)):
        real, pred, nivel = [], [], []
        for v in prueba:
            b = regla_de_hoy(v, filas, historia)[0]
            x = modelo.predecir(v, b)
            e = exceso(v, b) - m.correccion(v)
            real.append(float(e[0] + e[1])); pred.append(x["exceso_arranque_pp"] / 100); nivel.append(x["nivel"])
        real, pred, nivel = np.array(real), np.array(pred), np.array(nivel)
        perdio = real > 0
        r[nombre] = {
            "n": len(prueba),
            "corr_exceso_arranque": round(float(np.corrcoef(pred, real)[0, 1]), 3),
            "pct_que_perdio_de_mas": round(100 * float(perdio.mean()), 1),
            "base_ic95": wilson(int(perdio.sum()), len(prueba)),
            "por_nivel": {k: {"n": int((nivel == k).sum()),
                              "pct_perdio_de_mas": round(100 * float(perdio[nivel == k].mean()), 1) if (nivel == k).any() else None,
                              "ic95": wilson(int(perdio[nivel == k].sum()), int((nivel == k).sum())),
                              "exceso_real_mediano_pp": round(100 * float(np.median(real[nivel == k])), 1) if (nivel == k).any() else None}
                          for k in ("alto", "medio", "bajo")},
        }
    return r


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--voz", type=Path, required=True)
    ap.add_argument("--salida", type=Path, help="Guarda el modelo entrenado con todo (privado).")
    ap.add_argument("--publico", type=Path, help="Guarda también la versión sin talentos, la que puede ir al repo.")
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
    if a.salida or a.publico:
        m = Arranque.entrenar(filas, voz, FIN_PRUEBA)
        if a.salida:
            m.guardar(a.salida)
            print(f"modelo guardado en {a.salida}")
        if a.publico:
            m.guardar(a.publico, publico=True)
            print(f"versión pública (sin talentos) en {a.publico}")


if __name__ == "__main__":
    main()
