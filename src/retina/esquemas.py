"""Esquema JSON del tramo (v1), el contrato de salida del servicio «describir».

Los valores posibles de riesgo_anzuelo salen de reglas/anzuelos-v1.json:
la regla vive en un archivo que edita una persona, no en el código.
Spark 1.3 no oye bien el audio dentro del MP4, así que voz y silencios no
están aquí: salen de Voice Transcribe.

Uso:
    python -m retina.esquemas > esquemas/tramo-v1.json
"""
from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
VERSION = "tramo-v1"

TIPOS_DE_GANCHO = [
    "pregunta", "dato_impactante", "promesa", "conflicto", "imagen_impactante",
    "presentacion_del_talento", "ninguno", "otro",
]
TIPOS_DE_PLANO = ["primer_plano", "plano_medio", "plano_abierto", "grafico", "texto_solo", "otro"]


def ids_anzuelos(ruta: Path = RAIZ / "reglas" / "anzuelos-v1.json") -> list[str]:
    return [a["id"] for a in json.loads(ruta.read_text(encoding="utf-8"))["anzuelos"]]


def _objeto(propiedades: dict) -> dict:
    # Modo estricto de la API: sin campos extra y todos obligatorios.
    return {"type": "object", "additionalProperties": False,
            "properties": propiedades, "required": list(propiedades)}


def esquema_tramo() -> dict:
    tramo = _objeto({
        "tramo": {"type": "integer", "description": "Índice del tramo, de 0 a 39."},
        "presentador_en_pantalla": {"type": "boolean"},
        "texto_en_pantalla": {"type": "string",
                              "description": "Texto visible copiado tal cual; vacío si no hay."},
        "cambio_de_plano": {"type": "boolean",
                            "description": "Hay al menos un corte o cambio de plano dentro del tramo."},
        "tipo_de_plano": {"type": "string", "enum": TIPOS_DE_PLANO},
        "tipo_de_gancho": {"type": "string", "enum": TIPOS_DE_GANCHO,
                           "description": "Solo en los primeros tramos; después, ninguno."},
        "riesgo_anzuelo": {"type": "string", "enum": ["ninguno", *ids_anzuelos()]},
        "que_pasa": {"type": "string", "description": "Una frase: qué se ve en el tramo."},
    })
    return _objeto({
        "version_esquema": {"type": "string", "enum": [VERSION]},
        "tramos": {"type": "array", "items": tramo},
        "no_pude_verificar": {"type": "array", "items": {"type": "string"},
                              "description": "Lo que no se pudo ver o confirmar en el video."},
    })


def formato_responses() -> dict:
    """Bloque text.format para /v1/responses (en Responses no va response_format)."""
    return {"format": {"type": "json_schema", "name": "tramos_v1", "strict": True,
                       "schema": esquema_tramo()}}


if __name__ == "__main__":
    print(json.dumps(esquema_tramo(), ensure_ascii=False, indent=2))
