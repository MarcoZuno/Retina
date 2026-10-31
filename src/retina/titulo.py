"""Servicio «titulo»: ¿el video entrega lo que promete su título?

Las comprobaciones de Retina parten del título. Si el título promete algo que el video no da, todas pueden salir bien y
nadie lo avisaría. Muse Spark 1.3 lo juzga con lo que se dice y lo que se lee en pantalla. Es un aviso: el título no se toca.
Si Spark falla o su frase no pasa el filtro, no hay aviso; nunca se inventa uno.
"""
from __future__ import annotations

import json
import re

from . import integridad, meta_api
from .esquemas import RAIZ

MODELO = "muse-spark-1.3"
MAX_PALABRAS = 1500
ENLACE = re.compile(r"https?://|www\.", re.I)
SIN_DATO = {"cumple": None, "por_que": ""}
ESQUEMA = {"type": "object", "additionalProperties": False, "required": ["cumple", "por_que"], "properties": {
    "cumple": {"type": "string", "enum": ["si", "parcial", "no"]}, "por_que": {"type": "string"}}}


def instrucciones() -> str:
    return (RAIZ / "skills" / "titulo.md").read_text(encoding="utf-8").split("---", 2)[2].strip()


def aceptable(s: dict) -> bool:
    frase = s.get("por_que") or ""
    return s.get("cumple") in ("si", "parcial", "no") and bool(frase.strip()) and not ENLACE.search(frase) and not integridad.revisar(frase)


def revisar(titulo: str, dicho: str, pantalla: str, idioma: str = "es") -> dict:
    if not titulo.strip() or not (dicho.strip() or pantalla.strip()):
        return dict(SIN_DATO)
    datos = {"titulo": titulo, "lo_que_se_dice": " ".join(dicho.split()[:MAX_PALABRAS]), "texto_en_pantalla": pantalla[:2000],
             "idioma_de_la_respuesta": "inglés" if idioma == "en" else "español"}
    cuerpo = {"model": MODELO, "reasoning": {"effort": "low"}, "max_output_tokens": 3000, "store": False,
              "text": {"format": {"type": "json_schema", "name": "titulo_v1", "strict": True, "schema": ESQUEMA}},
              "input": [{"type": "message", "role": "developer", "content": [{"type": "input_text", "text": instrucciones()}]},
                        {"type": "message", "role": "user", "content": [
                            {"type": "input_text", "text": meta_api.como_dato("DATOS", json.dumps(datos, ensure_ascii=False))}]}]}
    try:
        s = json.loads(meta_api.texto_de(meta_api.responder("titulo", cuerpo)))
    except meta_api.TopeAlcanzado:
        raise
    except Exception:  # noqa: BLE001 — sin respuesta no hay aviso; la revisión sigue
        return dict(SIN_DATO)
    return {"cumple": s["cumple"], "por_que": s["por_que"].strip()} if aceptable(s) else dict(SIN_DATO)
