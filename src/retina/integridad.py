"""Filtro de integridad: las reglas deciden, la IA solo propone.

Toda sugerencia de Retina pasa por aquí antes de llegar a la persona. Si
contiene una frase de la lista de anzuelos (reglas/anzuelos-v1.json), se
bloquea y se dice cuál regla rompió. El modelo nunca puede saltarse esto
porque corre en código, después del modelo.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
REGLAS = RAIZ / "reglas" / "anzuelos-v1.json"


# Letras de otros alfabetos que se ven iguales a las latinas («сomenta» con c cirílica).
HOMOGLIFOS = str.maketrans("аеорсухіјѕԁɡ", "aeopcyxijsdg")
# Números y signos que imitan letras, solo dentro de palabras («c0menten»), no en «3 días».
IMITACIONES = str.maketrans("013457@$", "oieastas")


def normalizar(texto: str) -> str:
    t = texto.lower().translate(HOMOGLIFOS)
    t = re.sub(r"(?<=[^\W\d_])[-._*](?=[^\W\d_])", "", t)  # co-menten, c.o.m.e.n.t.e.n
    t = re.sub(r"\b(?=\w*[a-z])(?=\w*[0-9@$])[\w@$]+", lambda m: m.group(0).translate(IMITACIONES), t)
    sin_acentos = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sin_acentos)


@lru_cache(maxsize=1)
def reglas() -> dict:
    return json.loads(REGLAS.read_text(encoding="utf-8"))


def revisar(texto: str) -> list[dict]:
    """Devuelve las reglas que rompe el texto (vacío si pasa)."""
    t = f" {normalizar(texto)} "
    rotas = []
    for a in reglas()["anzuelos"]:
        # «coment*» cubre comenta, comenten, comentarios…; sin asterisco es palabra exacta.
        hallazgos = [f for f in a.get("frases", [])
                     if re.search(rf"\b{re.escape(normalizar(f).rstrip('*'))}{r'\w*' if f.endswith('*') else r'\b'}", t)]
        hallazgos += [e for e in a.get("emojis", []) if e in texto]  # los emojis se pierden al normalizar
        if hallazgos:
            rotas.append({"id": a["id"], "regla": a["nombre"], "fuente": a["fuente"], "frases": hallazgos})
    return rotas


if __name__ == "__main__":
    import sys
    print(json.dumps(revisar(" ".join(sys.argv[1:])), ensure_ascii=False, indent=1))
