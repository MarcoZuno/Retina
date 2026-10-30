"""Muse Spark Open (pesos abiertos de Meta) servido por Baseten, con tope de gasto propio.

API compatible con Chat Completions de OpenAI. La llave va en el .env fuera del repo como
BASETEN_API_KEY; nunca en el código. El costo de cada llamada se anota en costos.jsonl junto
con el de la API de Meta. Baseten tiene su propio tope (TOPE_BASETEN_USD) y además respeta el tope del
usuario (RETINA_TOPE_USD); cada llamada aparta su peor caso antes de salir (meta_api.reservar).

Uso (prueba de humo):
    python -m retina.baseten
"""
from __future__ import annotations

import os
import time

from . import meta_api

BASE = "https://inference.baseten.co/v1"
MODELO = os.environ.get("RETINA_SPARK_OPEN", "meta-models/muse-spark-open-1026")  # id de la guía del concurso
TOPE_BASETEN_USD = 75.0  # tope propio de Baseten: deja margen en los USD 100 de créditos del concurso
PRECIO = (1.25, 0.15, 4.25)  # USD por millón (entrada, entrada en caché, salida), igual que Spark en la API de Meta


def _llave() -> str:
    meta_api._cargar_env()
    llave = os.environ.get("BASETEN_API_KEY", "")
    if not llave:
        raise RuntimeError("Falta BASETEN_API_KEY. Ponla en el .env de la raíz del repo (ver .env.example) o define la variable de entorno.")
    return llave


def gastado_usd() -> float:
    """Lo anotado de Baseten (los servicios «baseten-…» del registro de costos)."""
    return meta_api.gastado_usd("baseten")


def _reservar(servicio: str, max_tokens: int) -> str:
    """Aparta el peor caso de la llamada. Respeta los dos topes: el de Baseten y el del usuario
    (RETINA_TOPE_USD, el mismo de la API de Meta, que cuenta todo el gasto del registro)."""
    peor = max_tokens * PRECIO[2] / 1e6
    return meta_api.reservar(f"baseten-{servicio}", peor, "baseten", TOPE_BASETEN_USD)


def usd(uso) -> float:
    entrada = getattr(uso, "prompt_tokens", 0) or 0
    detalle = getattr(uso, "prompt_tokens_details", None)
    cache = (getattr(detalle, "cached_tokens", 0) or 0) if detalle else 0
    salida = getattr(uso, "completion_tokens", 0) or 0
    return ((entrada - cache) * PRECIO[0] + cache * PRECIO[1] + salida * PRECIO[2]) / 1e6


def completar(servicio: str, mensajes: list[dict], max_tokens: int = 8000, esfuerzo: str | None = None,
              herramientas: list[dict] | None = None, temperatura: float | None = None):
    """Devuelve el mensaje de la respuesta: su texto y, si se le dieron herramientas, las que llamó.
    `esfuerzo` (low, medium, high) es el razonamiento; Spark Open en Baseten lo respeta (Meta, 27-oct)."""
    from openai import OpenAI

    llave = _llave()  # sin llave no se aparta nada
    reserva = _reservar(servicio, max_tokens)
    cliente = OpenAI(api_key=llave, base_url=BASE, timeout=meta_api.TIEMPO[1], max_retries=2)
    t0 = time.time()
    extra = {"reasoning_effort": esfuerzo} if esfuerzo else {}
    if herramientas:
        extra["tools"] = herramientas
    if temperatura is not None:  # 0 = el mismo video da la misma respuesta
        extra["temperature"] = temperatura
    try:
        r = cliente.chat.completions.create(model=MODELO, messages=mensajes, max_tokens=max_tokens, **extra)
    except Exception as e:
        if getattr(e, "status_code", None) is not None:  # la API contestó con error: no cobró
            meta_api.liberar(reserva)
        raise  # sin respuesta (red, tiempo): no sabemos si cobró, la reserva se queda hasta que venza
    meta_api._registrar(f"baseten-{servicio}", MODELO, time.time() - t0, usd(r.usage), reserva,
                        entrada=getattr(r.usage, "prompt_tokens", 0), salida=getattr(r.usage, "completion_tokens", 0))
    return r.choices[0].message


def chat(servicio: str, mensajes: list[dict], esquema: dict | None = None, max_tokens: int = 8000,
         esfuerzo: str | None = None, temperatura: float | None = None) -> str:
    """Devuelve el texto de la respuesta. `esquema` se ignora aquí: lo describe quien arma los mensajes."""
    # Spark Open en las Model APIs de Baseten no acepta salida estructurada ni modo JSON (docs de Baseten,
    # 28-oct-2026): el formato se pide en las instrucciones y el validador de Retina revisa lo demás.
    return completar(servicio, mensajes, max_tokens, esfuerzo, temperatura=temperatura).content or ""


def main() -> None:
    texto = chat("humo", [{"role": "user", "content": 'Responde solo con este JSON: {"ok": true}'}], max_tokens=1000)
    print(texto, f"· gastado en Baseten: USD {gastado_usd():.4f}")


if __name__ == "__main__":
    main()
