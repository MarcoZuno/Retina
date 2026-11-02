"""Cerebro público de Retina: lo que aprendió de la retención, sin ningún video.

Es lo que va en el repo para que cualquiera revise su propio video sin los datos
de la empresa. Se entrena solo con los videos marcados como elegibles en la base (columna
«incluir», calculada fuera del repo) y sin nombres de talentos en las palabras. Lo que sale es un JSON con pesos y cinco curvas
promedio por duración: ningún título, talento, código ni cifra de un video.

Adentro van dos piezas:
- el cerebro para cualquier video (duración, reel, hora y día, título y voz del
  arranque), el mismo que se midió con talentos escondidos (eval/cualquier_video.py);
Sin voz, la curva es la de los videos de su duración y la tarjeta lo dice.

Uso (con la base privada):
    python -m retina.publico --base BASE.csv --voz VOZ.jsonl --salida modelos/retina-publico.json
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from datetime import timedelta
from pathlib import Path

import numpy as np

from .curvas import CUBETAS, VENTANA, cargar, regla_de_hoy, tramo_exceso
from .predecir import (LAMBDA_UNIVERSAL, N_ARRANQUE, N_PALABRAS, Rasgos, ajustar_ridge, de_fuera,
                       en_bloques, fijos_universales, plano, rasgos_universales)

RAIZ = Path(__file__).resolve().parents[2]
VERSION = "retina-publico-v1"
# Personas de cada 100 por las que suele fallar, en creadores escondidos y videos posteriores al entrenamiento: el número, y
# el promedio de su duración cuando no hay voz para ajustarlo (eval/margen_numero.py, docs/numero.md).
MARGEN_PERSONAS, MARGEN_PROMEDIO = 11, 12
N_CUBETAS = len(CUBETAS) - 1


def motivo_fuera(v: dict) -> str | None:
    """Por qué un video no entra al cerebro público, o None si entra. Solo entran los marcados como elegibles; sin dato, fuera."""
    return None if v.get("incluir") is True else "no_elegible"


def firma(titulo: str) -> str:
    """El nombre que algunos títulos llevan al final, después de un emoji («… 😱 Ana Pérez»)."""
    simbolos = [i for i, c in enumerate(titulo) if unicodedata.category(c) == "So"]
    if not simbolos:
        return ""
    cola = titulo[simbolos[-1] + 1:]
    palabras = re.findall(r"[^\W\d_]+", cola)
    if 1 <= len(palabras) <= 6 and all(p[0].isupper() or p == "y" for p in palabras):
        return cola
    return ""


def nombres(filas: list[dict]) -> frozenset:
    """Palabras de nombres de talentos: las de la lista de talentos y las que firman títulos 3 veces o más."""
    de_lista = {plano(p) for v in filas for p in re.findall(r"[^\W\d_]{3,}", v["talento"])}
    firmas = Counter(plano(p) for v in filas for p in re.findall(r"[^\W\d_]{3,}", firma(v.get("titulo", ""))))
    return frozenset(de_lista | {p for p, n in firmas.items() if n >= 3})


def titulo_publico(titulo: str, quitar: frozenset) -> str:
    sin = titulo[: len(titulo) - len(firma(titulo))] if firma(titulo) else titulo
    return " ".join(p for p in sin.split() if plano(re.sub(r"[^\w]", "", p)) not in quitar)


def entrenar(filas: list[dict], voz: dict, fichas: dict | None = None) -> dict:
    """`fichas` (retina.ficha, por código): si vienen, la ficha del arranque entra como rasgo del número."""
    from .ficha import ficha_a_vector
    quedan = [v for v in filas if motivo_fuera(v) is None]
    quitar = nombres(filas)
    # Como llega un video de fuera: sin talento, sin código y con el título sin nombres.
    limpios = [{**v, "titulo": titulo_publico(v.get("titulo", ""), quitar)} for v in quedan]
    afuera = [de_fuera(v) for v in limpios]
    bases = [regla_de_hoy(f, quedan, quedan)[0] for f in afuera]
    X = np.array([rasgos_universales(f, b, fijos_universales(f["archivo"], voz.get(v["codigo"]), v["dur"], quitar))
                  for f, v, b in zip(afuera, quedan, bases)])
    if fichas:
        X = np.hstack([X, np.array([ficha_a_vector(fichas.get(v["codigo"])) for v in quedan])])
    W = ajustar_ridge(X, np.array([v["curva"] - b for v, b in zip(quedan, bases)]), LAMBDA_UNIVERSAL)

    hasta = max(v["fecha"] for v in quedan)
    curvas = []
    for c in range(N_CUBETAS):
        recientes = [v["curva"] for v in quedan if v["cubeta"] == c and v["fecha"] > hasta - VENTANA]
        grupo = recientes if len(recientes) >= 15 else [v["curva"] for v in quedan if v["cubeta"] == c]
        grupo = grupo or [v["curva"] for v in quedan]  # una duración sin videos toma el promedio de todos
        curvas.append(np.mean(grupo, axis=0).tolist())

    redondo = lambda a: np.round(np.asarray(a, dtype=float), 6).tolist()  # noqa: E731
    return {
        "version": VERSION,
        "que_es": "Lo que Retina aprendió de la retención de una página grande de Facebook en México, sin ningún "
                  "video: pesos y curvas promedio por duración. No trae títulos, talentos, códigos, ingresos ni cifras "
                  "de un video.",
        "datos_hasta": hasta.strftime("%Y-%m-%d"),
        "rasgos": {"n_palabras": N_PALABRAS, "n_arranque": N_ARRANQUE, "lambda": LAMBDA_UNIVERSAL, "ficha": bool(fichas),
                   "cubetas_s": CUBETAS[:-1]},
        "curvas_por_duracion": [redondo(c) for c in curvas],
        "cualquier_video": redondo(W),
    }


class ModeloPublico:
    """El cerebro público listo para un video. Se carga de JSON (no ejecuta código al abrirse)."""

    filas: list = []  # sin historia: no hay talentos que listar
    # El semáforo no pasó su regla sellada con videos de fuera (eval/semaforo_publico.py, 29-oct) y la v2
    # (eval/semaforo_publico_v2.py) es un reajuste en los mismos periodos: el modo público no lo muestra
    # (docs/decisiones.md). El número se queda como referencia.
    semaforo = False

    def __init__(self, d: dict):
        if d.get("version") != VERSION:
            raise ValueError(f"No es un cerebro público de Retina ({d.get('version')}).")
        self.d = d
        self.curvas = [np.array(c) for c in d["curvas_por_duracion"]]
        self.W = np.array(d["cualquier_video"])

    @classmethod
    def cargar(cls, ruta: Path) -> "ModeloPublico":
        return cls(json.loads(Path(ruta).read_text(encoding="utf-8")))

    def de_la_casa(self, v: dict) -> bool:
        return False

    def curva(self, v: dict, bloques: list | None, ficha: dict | None = None) -> tuple[np.ndarray, np.ndarray]:
        """(curva predicha, curva de videos como el tuyo). `bloques`: la voz ya en bloques [inicio_s, texto], como se guarda
        para entrenar; `predecir` los arma desde los tramos del transcriptor y `eval/margen_numero.py` los lee del archivo de
        voz, para que el margen se mida con esta misma función. Sin voz, el número es la curva de su duración."""
        base = self.curvas[v["cubeta"]]
        if not bloques:
            return base.copy(), base
        f = de_fuera(v)
        x = rasgos_universales(f, base, fijos_universales(f["archivo"], bloques, v["dur"]))
        if self.d["rasgos"].get("ficha"):
            from .ficha import ficha_a_vector
            x = np.concatenate([x, ficha_a_vector(ficha)])
        return np.clip(base + x @ self.W, 0, 1), base

    def predecir(self, v: dict, emb=None, audio=None, tramos: list | None = None, ficha: dict | None = None) -> dict:
        p, base = self.curva(v, en_bloques(tramos) if tramos else None, ficha)
        t = tramo_exceso(p, base)
        return {
            "curva_predicha": [round(float(x), 4) for x in p],
            "curva_parecidos": [round(float(x), 4) for x in base],
            "margen_personas": MARGEN_PERSONAS if tramos else MARGEN_PROMEDIO,
            "tramo_riesgo": t,
            "caida_predicha_pp": round(float((p[t] - p[t + 1]) * 100), 1),
            "caida_parecidos_pp": round(float((base[t] - base[t + 1]) * 100), 1),
            "regla_de_parecidos": "publica",
            "n_parecidos": None,  # el archivo público no dice cuántos videos tiene la página
            "uso_video": False,
            "cerebro": "cualquier_video" if tramos else "promedio",
            "conoce_al_creador": False,
            "uso_voz": bool(tramos),
            # Casi no hay reels ni videos de menos de 30 s o de más de 4 min en la base: el número es una referencia más débil.
            "formato_poco_conocido": v["cubeta"] in (0, N_CUBETAS - 1) or bool(v.get("reel")),
            "datos_hasta": self.d["datos_hasta"],
        }


def cargar_modelo(ruta: Path):
    """Un .json es el cerebro público; un .pkl, el modelo privado de la casa (solo archivos propios)."""
    if Path(ruta).suffix == ".json":
        return ModeloPublico.cargar(ruta)
    from .predecir import Modelo
    return Modelo.cargar(ruta)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--voz", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--fichas", type=Path, help="Fichas del arranque (retina.ficha): entran al número.")
    a = ap.parse_args()
    voz = {}
    for linea in a.voz.open(encoding="utf-8"):
        d = json.loads(linea); voz[d["codigo"]] = d["tramos"]
    filas = cargar(a.base)
    fichas = None
    if a.fichas:
        fichas = {}
        for linea in a.fichas.open(encoding="utf-8"):
            d = json.loads(linea); fichas[d.pop("codigo")] = d
    r = entrenar(filas, voz, fichas)
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    # Los conteos se quedan en la consola de quien lo arma: no van en el archivo público.
    print(f"{a.salida}: datos al {r['datos_hasta']} · {a.salida.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
