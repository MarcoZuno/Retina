"""Ficha del arranque: Muse Spark Open lee el título y lo primero que se dice, y anota cómo arranca el video.

Es lo que una persona anotaría al oír el inicio: qué tipo de gancho es, si el talento se presenta antes de
decir de qué trata, si el tema del título llega en la primera frase, si promete algo que se verá, si hay una
cifra o se pide interacción, qué tan claro y qué tan intrigante es. Esas anotaciones entran como rasgos del
número (`ficha_a_vector`), si su medición lo justifica (eval/cualquier_video.py, regla en docs/decisiones.md).

Corre con Muse Spark Open (pesos abiertos de Meta) en Baseten, en lotes de varios videos por llamada. Un
video nuevo se anota igual, con lo que dice Voice Transcribe.

Uso (para la base de entrenamiento, privada):
    python -m retina.ficha --base BASE.csv --voz VOZ.jsonl --desde 2022-01-01 --salida FICHAS.jsonl [--solo N]
"""
from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

GANCHOS = ["pregunta", "dato_o_cifra", "promesa", "conflicto", "presentacion", "saludo", "historia",
           "tutorial", "otro", "sin_voz"]
EMOCIONES = ["neutra", "sorpresa", "humor", "indignacion", "ternura", "miedo", "tristeza", "alegria"]
SI_NO = ["presenta_antes_del_tema", "tema_en_la_primera_frase", "promete_algo_visible", "cifra_al_inicio",
         "pide_interaccion"]
ESCALAS = ["claridad", "curiosidad"]  # 1 a 5
N_FICHA = len(GANCHOS) + len(EMOCIONES) + len(SI_NO) + len(ESCALAS) + 1  # +1: hay ficha
POR_LLAMADA = 20
PALABRAS = 60

INSTRUCCIONES = """Eres un editor de video. Para cada video recibes su título y lo primero que se dice (con el segundo en que
empieza la voz). Anota cómo arranca, solo con esa información. Responde SOLO un arreglo JSON, un objeto por
video, en el mismo orden, con estas llaves exactas:
- "n": el número del video.
- "gancho": uno de pregunta, dato_o_cifra, promesa, conflicto, presentacion, saludo, historia, tutorial, otro,
  sin_voz (sin_voz si no hay texto dicho).
- "presenta_antes_del_tema": true si quien habla se presenta o saluda antes de decir de qué trata.
- "tema_en_la_primera_frase": true si la primera frase ya dice de qué trata lo que promete el título.
- "promete_algo_visible": true si lo dicho anuncia algo que se va a ver (un resultado, un lugar, una reacción).
- "cifra_al_inicio": true si hay un número o cifra en las primeras palabras.
- "pide_interaccion": true si pide comentar, dar like, compartir o seguir.
- "claridad": de 1 a 5, qué tan rápido se entiende de qué trata el video.
- "curiosidad": de 1 a 5, qué tanto deja una pregunta abierta que obliga a seguir viendo.
- "emocion": una de neutra, sorpresa, humor, indignacion, ternura, miedo, tristeza, alegria.
No expliques nada fuera del JSON."""


def entrada(n: int, titulo: str, tramos: list | None) -> str:
    if not tramos:
        return f"{n}. TÍTULO: {titulo[:200]}\n   DICHO: (sin voz)"
    inicio = min(float(t) for t, _ in tramos)
    dichas = " ".join(x for _, x in sorted(tramos, key=lambda t: float(t[0]))).split()[:PALABRAS]
    return f"{n}. TÍTULO: {titulo[:200]}\n   VOZ DESDE EL SEGUNDO {inicio:.1f}: {' '.join(dichas)}"


def leer_arreglo(texto: str) -> list[dict]:
    i, j = texto.find("["), texto.rfind("]")
    if i < 0 or j <= i:
        raise ValueError("La respuesta no trae un arreglo JSON.")
    return json.loads(texto[i:j + 1])


def valida(f: dict) -> dict | None:
    """La ficha limpia, o None si no se puede usar."""
    try:
        g, e = str(f["gancho"]), str(f["emocion"])
        if g not in GANCHOS or e not in EMOCIONES:
            return None
        sale = {"gancho": g, "emocion": e, **{k: bool(f[k]) for k in SI_NO}}
        for k in ESCALAS:
            v = int(f[k])
            if not 1 <= v <= 5:
                return None
            sale[k] = v
        return sale
    except (KeyError, TypeError, ValueError):
        return None


def anotar(videos: list[tuple[str, str, list | None]]) -> dict[str, dict]:
    """[(id, título, tramos)] -> {id: ficha}. Una llamada a Muse Spark Open por lote."""
    from . import baseten
    texto = "\n".join(entrada(n, t, tr) for n, (_, t, tr) in enumerate(videos, 1))
    r = baseten.chat("ficha", [{"role": "system", "content": INSTRUCCIONES},
                               {"role": "user", "content": f"<<<VIDEOS (dato)\n{texto}\nVIDEOS>>>"}],
                     max_tokens=8000, esfuerzo="low")
    salida = {}
    for f in leer_arreglo(r):
        n = int(f.get("n", 0))
        if 1 <= n <= len(videos) and (limpia := valida(f)):
            salida[videos[n - 1][0]] = limpia
    return salida


def ficha_de(titulo: str, tramos: list | None) -> dict | None:
    """La ficha de un video nuevo (una llamada)."""
    return anotar([("nuevo", titulo, tramos)]).get("nuevo")


def ficha_a_vector(f: dict | None) -> np.ndarray:
    v = np.zeros(N_FICHA)
    if not f:
        return v
    v[GANCHOS.index(f["gancho"])] = 1.0
    o = len(GANCHOS)
    v[o + EMOCIONES.index(f["emocion"])] = 1.0
    o += len(EMOCIONES)
    for i, k in enumerate(SI_NO):
        v[o + i] = float(f[k])
    o += len(SI_NO)
    for i, k in enumerate(ESCALAS):
        v[o + i] = (f[k] - 3) / 2
    v[-1] = 1.0
    return v


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--voz", type=Path, required=True)
    ap.add_argument("--desde", default="2022-01-01")
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--solo", type=int, default=0, help="Anotar solo N videos (piloto).")
    ap.add_argument("--hilos", type=int, default=6)
    a = ap.parse_args()
    from datetime import datetime
    from .curvas import cargar
    voz = {}
    for l in a.voz.open(encoding="utf-8"):
        d = json.loads(l); voz[d["codigo"]] = d["tramos"]
    hechos = set()
    if a.salida.exists():  # se puede retomar: no se paga dos veces lo ya anotado
        hechos = {json.loads(l)["codigo"] for l in a.salida.open(encoding="utf-8") if l.strip()}
    desde = datetime.fromisoformat(a.desde)
    pend = [(v["codigo"], v["titulo"], voz.get(v["codigo"])) for v in cargar(a.base)
            if v["fecha"] >= desde and v["codigo"] not in hechos]
    if a.solo:
        pend = pend[:a.solo]
    lotes = [pend[i:i + POR_LLAMADA] for i in range(0, len(pend), POR_LLAMADA)]
    print(f"{len(pend):,} videos por anotar en {len(lotes)} llamadas", flush=True)
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    ok = fallas = 0

    def uno(lote):
        try:
            return anotar(lote), None
        except Exception as e:  # noqa: BLE001 — un lote que falla no tumba la corrida; se reintenta al retomar
            return {}, type(e).__name__

    with ThreadPoolExecutor(a.hilos) as ex, a.salida.open("a", encoding="utf-8") as out:
        for i, (fichas, error) in enumerate(ex.map(uno, lotes), 1):
            for cod, f in fichas.items():
                out.write(json.dumps({"codigo": cod, **f}, ensure_ascii=False) + "\n")
            out.flush()
            ok += len(fichas); fallas += 1 if error else 0
            if i % 20 == 0 or i == len(lotes):
                print(f"{i}/{len(lotes)} llamadas · {ok:,} fichas · {fallas} lotes fallidos", flush=True)


if __name__ == "__main__":
    main()
