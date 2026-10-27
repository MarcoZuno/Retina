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


def normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sin_acentos.lower())


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
        if hallazgos:
            rotas.append({"id": a["id"], "regla": a["nombre"], "fuente": a["fuente"], "frases": hallazgos})
    return rotas


if __name__ == "__main__":
    import sys
    print(json.dumps(revisar(" ".join(sys.argv[1:])), ensure_ascii=False, indent=1))
