"""Muse Spark Open (pesos abiertos de Meta) servido por Baseten, con tope de gasto propio.

API compatible con Chat Completions de OpenAI. La llave va en el .env fuera del repo como
BASETEN_API_KEY; nunca en el código. El costo de cada llamada se anota en costos.jsonl junto
con el de la API de Meta, pero Baseten tiene su propio tope (TOPE_BASETEN_USD).

Uso (prueba de humo):
    python -m retina.baseten
"""
from __future__ import annotations

import json
import os
import time

from . import meta_api

BASE = "https://inference.baseten.co/v1"
MODELO = os.environ.get("RETINA_SPARK_OPEN", "meta-models/muse-spark-open-1026")  # id de la guía del concurso
TOPE_BASETEN_USD = 30.0  # de los USD 100 de créditos de Baseten; subirlo es cambiar esto
PRECIO = (1.25, 0.15, 4.25)  # USD por millón (entrada, entrada en caché, salida), igual que Spark en la API de Meta


def _llave() -> str:
    meta_api._cargar_env()
    llave = os.environ.get("BASETEN_API_KEY", "")
    if not llave:
        raise RuntimeError("Falta BASETEN_API_KEY en tu .env (nunca dentro del repo).")
    return llave


def gastado_usd() -> float:
    if not meta_api.COSTOS.exists():
        return 0.0
    return sum(json.loads(l).get("usd", 0.0) for l in meta_api.COSTOS.read_text(encoding="utf-8").splitlines()
               if l.strip() and json.loads(l).get("servicio", "").startswith("baseten"))


def _revisar_tope(max_tokens: int) -> None:
    peor = max_tokens * PRECIO[2] / 1e6
    if gastado_usd() + peor > TOPE_BASETEN_USD:
        raise meta_api.TopeAlcanzado(f"Tope de Baseten: llevamos {gastado_usd():.2f} USD de {TOPE_BASETEN_USD:.2f}.")


def usd(uso) -> float:
    entrada = getattr(uso, "prompt_tokens", 0) or 0
    detalle = getattr(uso, "prompt_tokens_details", None)
    cache = (getattr(detalle, "cached_tokens", 0) or 0) if detalle else 0
    salida = getattr(uso, "completion_tokens", 0) or 0
    return ((entrada - cache) * PRECIO[0] + cache * PRECIO[1] + salida * PRECIO[2]) / 1e6


def chat(servicio: str, mensajes: list[dict], esquema: dict | None = None, max_tokens: int = 8000) -> str:
    """Devuelve el texto de la respuesta. Con esquema pide JSON estricto; si el servidor no lo
    acepta, pide JSON simple y el validador de Retina revisa lo demás."""
    from openai import BadRequestError, OpenAI

    _revisar_tope(max_tokens)
    cliente = OpenAI(api_key=_llave(), base_url=BASE, timeout=meta_api.TIEMPO[1], max_retries=2)
    formatos = ([{"type": "json_schema", "json_schema": {"name": "retina", "strict": True, "schema": esquema}}]
                if esquema else []) + [{"type": "json_object"}]
    t0 = time.time()
    for i, formato in enumerate(formatos):
        try:
            r = cliente.chat.completions.create(model=MODELO, messages=mensajes, max_tokens=max_tokens,
                                                response_format=formato)
            break
        except BadRequestError:
            if i == len(formatos) - 1:
                raise
    meta_api._registrar(f"baseten-{servicio}", MODELO, time.time() - t0, usd(r.usage),
                        entrada=getattr(r.usage, "prompt_tokens", 0), salida=getattr(r.usage, "completion_tokens", 0),
                        formato=formato["type"])
    return r.choices[0].message.content or ""


def main() -> None:
    texto = chat("humo", [{"role": "user", "content": 'Responde solo con este JSON: {"ok": true}'}], max_tokens=50)
    print(texto, f"· gastado en Baseten: USD {gastado_usd():.4f}")


if __name__ == "__main__":
    main()
