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


INTENTOS = 3  # como en meta_api.responder: un 5xx a veces sí se cobra, y repetir de más puede cobrar doble


def _reservar(servicio: str, max_tokens: int, mensajes: list | None = None, herramientas: list | None = None) -> str:
    """Aparta el peor caso de la llamada: toda la salida permitida más la entrada que viaja (los mensajes completos,
    con llamadas y salidas de herramientas, y las definiciones de herramientas), estimada por lo alto. Respeta los dos
    topes: el de Baseten y el del usuario (RETINA_TOPE_USD, el mismo de la API de Meta, que cuenta todo el gasto)."""
    import json

    viaja = json.dumps(mensajes or [], ensure_ascii=False) + json.dumps(herramientas or [], ensure_ascii=False)
    entrada = len(viaja) // meta_api.CARACTERES_POR_TOKEN + 1
    peor = (max_tokens * PRECIO[2] + entrada * PRECIO[0]) / 1e6
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
    reservas = [_reservar(servicio, max_tokens, mensajes, herramientas)]
    # Los reintentos los lleva Retina y no el cliente: cada intento que pudo cobrarse aparta lo suyo.
    cliente = OpenAI(api_key=llave, base_url=BASE, timeout=meta_api.TIEMPO[1], max_retries=0)
    t0 = time.time()
    extra = {"reasoning_effort": esfuerzo} if esfuerzo else {}
    if herramientas:
        extra["tools"] = herramientas
    if temperatura is not None:  # 0 = el mismo video da la misma respuesta
        extra["temperature"] = temperatura
    for intento in range(INTENTOS):
        try:
            r = cliente.chat.completions.create(model=MODELO, messages=mensajes, max_tokens=max_tokens, **extra)
            break
        except Exception as e:
            estado = getattr(e, "status_code", None)
            if estado is not None and estado != 429 and estado < 500:  # la API contestó con error: no cobró
                for x in reservas:
                    meta_api.liberar(x)
                raise
            if intento == INTENTOS - 1:
                raise  # sin respuesta (red, tiempo) o 5xx repetido: no sabemos si cobró, lo apartado se queda hasta que venza
            if estado != 429:  # un 5xx o una falla de red a veces sí se cobran: ese intento se queda apartado y el siguiente aparta lo suyo
                reservas.append(_reservar(servicio, max_tokens, mensajes, herramientas))
            time.sleep(meta_api._espera(None, intento))
    meta_api._registrar(f"baseten-{servicio}", MODELO, time.time() - t0, usd(r.usage), reservas[-1],
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
