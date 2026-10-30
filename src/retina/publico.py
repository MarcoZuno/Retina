"""Cerebro público de Retina: lo que aprendió de la retención, sin ningún video.

Es lo que va en el repo para que cualquiera revise su propio video sin los datos
de la empresa. Se entrena solo con videos que no tuvieron elegibilidad y que no tocan
fuera de alcance ni temas fuera de alcance (reglas/alcance-v1.json), y sin nombres de
talentos en las palabras. Lo que sale es un JSON con pesos y cinco curvas
promedio por duración: ningún título, talento, código ni cifra de un video.

Adentro van dos piezas:
- el cerebro para cualquier video (duración, reel, hora y día, título y voz del
  arranque), el mismo que se midió con talentos escondidos (eval/cualquier_video.py);
- el riesgo del arranque sin talento ni tipo de producción (retina.arranque).
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

from .arranque import Arranque
from .curvas import CUBETAS, VENTANA, cargar, regla_de_hoy, tramo_exceso
from .predecir import (LAMBDA_UNIVERSAL, N_ARRANQUE, N_PALABRAS, Rasgos, ajustar_ridge, de_fuera,
                       en_bloques, fijos_universales, plano, rasgos_universales)

RAIZ = Path(__file__).resolve().parents[2]
TEMAS = RAIZ / "reglas" / "alcance-v1.json"
VERSION = "retina-publico-v1"
N_CUBETAS = len(CUBETAS) - 1


def patrones(ruta: Path = TEMAS) -> dict[str, re.Pattern]:
    reglas = json.loads(ruta.read_text(encoding="utf-8"))
    return {k: re.compile(r"\b(" + "|".join(re.escape(p) for p in reglas[k]) + ")") for k in ("fuera", "graves")}


def motivo_fuera(v: dict, tramos: list | None, temas: dict[str, re.Pattern]) -> str | None:
    """Por qué un video no entra al cerebro público, o None si entra. Ante la duda, fuera."""
    if v.get("elegibilidad") is None or v["elegibilidad"] > 0:
        return "elegibilidad"
    dichas = " ".join(x for _, x in sorted(tramos or [], key=lambda t: float(t[0]))).split()[:40]
    texto = plano(v.get("titulo", "") + " " + " ".join(dichas)) + " "
    for k, p in temas.items():
        if p.search(texto):
            return k
    return None


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
    temas = patrones()
    quedan = [v for v in filas if motivo_fuera(v, voz.get(v["codigo"]), temas) is None]
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

    # Riesgo del arranque: el mismo modelo de la casa, entrenado sin talento y con el título limpio;
    # los pesos de tipo de producción (códigos internos) no se publican.
    arr = Arranque.entrenar([{**v, "talento": "", "archivo": v["titulo"]} for v in limpios], voz, hasta + timedelta(minutes=1))
    ini, n_tipos = 1 + 5 + 7, len(arr.rasgos.tipos)
    pesos = {k: np.delete(w, range(ini, ini + n_tipos), axis=0) for k, w in arr.W.items()}

    redondo = lambda a: np.round(np.asarray(a, dtype=float), 6).tolist()  # noqa: E731
    return {
        "version": VERSION,
        "que_es": "Lo que Retina aprendió de la retención de una página grande de Facebook en México, sin ningún "
                  "video: pesos y curvas promedio por duración. No trae títulos, talentos, códigos, ingresos ni cifras "
                  "de un video. No aprendió de videos no elegibles ni de temas fuera de alcance o graves.",
        "datos_hasta": hasta.strftime("%Y-%m-%d"),
        "rasgos": {"n_palabras": N_PALABRAS, "n_arranque": N_ARRANQUE, "lambda": LAMBDA_UNIVERSAL, "ficha": bool(fichas),
                   "cubetas_s": CUBETAS[:-1]},
        "curvas_por_duracion": [redondo(c) for c in curvas],
        "cualquier_video": redondo(W),
        "arranque": {"W": {k: redondo(w) for k, w in pesos.items()}, "cortes": arr.cortes, "lambda": arr.lam},
    }


class ModeloPublico:
    """El cerebro público listo para un video. Se carga de JSON (no ejecuta código al abrirse)."""

    filas: list = []  # sin historia: no hay talentos que listar
    # El semáforo no pasó su regla sellada con videos de fuera (eval/semaforo_publico.py, 29-oct): el modo
    # público no lo muestra. El número sí pasó la suya (eval/cualquier_video.py) y se queda como referencia.
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

    def predecir(self, v: dict, emb=None, audio=None, tramos: list | None = None, ficha: dict | None = None) -> dict:
        base = self.curvas[v["cubeta"]]
        if tramos:
            f = de_fuera(v)
            x = rasgos_universales(f, base, fijos_universales(f["archivo"], en_bloques(tramos), v["dur"]))
            if self.d["rasgos"].get("ficha"):
                from .ficha import ficha_a_vector
                x = np.concatenate([x, ficha_a_vector(ficha)])
            p = np.clip(base + x @ self.W, 0, 1)
        else:
            p = base.copy()
        t = tramo_exceso(p, base)
        return {
            "curva_predicha": [round(float(x), 4) for x in p],
            "curva_parecidos": [round(float(x), 4) for x in base],
            "tramo_riesgo": t,
            "caida_predicha_pp": round(float((p[t] - p[t + 1]) * 100), 1),
            "caida_parecidos_pp": round(float((base[t] - base[t + 1]) * 100), 1),
            "regla_de_parecidos": "publica",
            "n_parecidos": None,  # el archivo público no dice cuántos videos tiene la página
            "uso_video": False,
            "cerebro": "cualquier_video" if tramos else "promedio",
            "conoce_al_creador": False,
            "uso_voz": bool(tramos),
            # Pocos videos de menos de 30 s en la base reciente: el número es una referencia más débil.
            "formato_poco_conocido": v["cubeta"] == 0,
            "datos_hasta": self.d["datos_hasta"],
        }

    def arranque(self) -> Arranque:
        a = self.d["arranque"]
        rasgos = Rasgos([]); rasgos.tipos, rasgos.talentos = [], []
        return Arranque(rasgos, {k: np.array(w) for k, w in a["W"].items()},
                        {k: tuple(c) for k, c in a["cortes"].items()}, a["lambda"], {k: None for k in a["W"]}, {})


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
