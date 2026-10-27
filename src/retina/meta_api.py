"""Envoltorio de la Meta Model API.

Toda llamada pasa por aquí: registra modelo, tokens, segundos y USD en
costos.jsonl, respeta el tope del proyecto y reintenta los 429 con espera
exponencial. La llave sale del entorno o de un .env fuera del repo; nunca se
imprime ni se escribe en los registros.
"""
from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path

import requests

BASE = os.environ.get("META_API_BASE", "https://api.meta.ai/v1")
RAIZ = Path(__file__).resolve().parents[2]
COSTOS = Path(os.environ.get("RETINA_COSTOS", RAIZ / "costos.jsonl"))
TOPE_USD = float(os.environ.get("RETINA_TOPE_USD", "100"))

# USD por millón de tokens (entrada, entrada en caché, salida), según
# dev.meta.ai/docs/pricing-rate-limits al 26-oct-2026.
PRECIOS_TOKENS = {
    "muse-spark-1.3": (1.25, 0.15, 4.25),
    "muse-wonder-1.0": (4.00, 0.20, 20.00),
}
PRECIO_IMAGEN = {"muse-image-1.0": 0.01}
PRECIO_HORA_AUDIO = {"muse-voice-transcribe-1.0": 0.18}


class TopeAlcanzado(RuntimeError):
    pass


def _cargar_env() -> None:
    """Lee RETINA_ENV (o un .env fuera del repo) sin pisar lo que ya exista."""
    ruta = Path(os.environ.get("RETINA_ENV", RAIZ.parent / "privado" / ".env"))
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        nombre, valor = linea.split("=", 1)
        os.environ.setdefault(nombre.strip(), valor.strip().strip('"'))


def _llave() -> str:
    _cargar_env()
    llave = os.environ.get("MODEL_API_KEY", "")
    if not llave:
        raise RuntimeError(
            "Falta MODEL_API_KEY. Ponla en tu .env "
            "(ver .env.example); nunca dentro del repo."
        )
    return llave


def gastado_usd() -> float:
    if not COSTOS.exists():
        return 0.0
    total = 0.0
    for linea in COSTOS.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            total += json.loads(linea).get("usd", 0.0)
    return total


def _revisar_tope(estimado_usd: float = 0.0) -> None:
    gastado = gastado_usd()
    if gastado + estimado_usd > TOPE_USD:
        raise TopeAlcanzado(
            f"Tope del proyecto: llevamos {gastado:.2f} USD y el tope es "
            f"{TOPE_USD:.2f}. Súbelo en tu .env si hace falta."
        )


def _registrar(servicio: str, modelo: str, segundos: float, usd: float, **extra) -> None:
    fila = {
        "fecha": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "servicio": servicio,
        "modelo": modelo,
        "segundos": round(segundos, 2),
        "usd": round(usd, 6),
        **extra,
    }
    COSTOS.parent.mkdir(parents=True, exist_ok=True)
    with COSTOS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(fila, ensure_ascii=False) + "\n")


def usd_tokens(modelo: str, uso: dict) -> float:
    entrada, cache, salida = PRECIOS_TOKENS.get(modelo, (0.0, 0.0, 0.0))
    en_cache = (uso.get("input_tokens_details") or {}).get("cached_tokens", 0) or 0
    sin_cache = max(uso.get("input_tokens", 0) - en_cache, 0)
    return (sin_cache * entrada + en_cache * cache + uso.get("output_tokens", 0) * salida) / 1e6


def _pedir(metodo: str, ruta: str, intentos: int = 5, **kwargs) -> requests.Response:
    """Petición con reintentos para 429 y 5xx (Retry-After o espera con jitter)."""
    cabeceras = kwargs.pop("headers", {})
    cabeceras["Authorization"] = f"Bearer {_llave()}"
    for intento in range(intentos):
        r = requests.request(metodo, f"{BASE}{ruta}", headers=cabeceras, timeout=600, **kwargs)
        if r.status_code != 429 and r.status_code < 500:
            return r
        espera = r.headers.get("Retry-After")
        espera = float(espera) if espera else min(60, 2 ** intento) + random.random()
        time.sleep(espera)
    return r


def _error(r: requests.Response) -> RuntimeError:
    # Solo estado y mensaje: nunca cabeceras ni la petición completa.
    try:
        msg = r.json().get("error", {}).get("message", "")
    except ValueError:
        msg = r.text[:300]
    return RuntimeError(f"HTTP {r.status_code}: {msg}")


def responder(servicio: str, cuerpo: dict) -> dict:
    """POST /v1/responses. Devuelve el JSON y registra el costo real (usage)."""
    _revisar_tope()
    t0 = time.time()
    r = _pedir("POST", "/responses", json=cuerpo)
    if r.status_code != 200:
        raise _error(r)
    datos = r.json()
    uso = datos.get("usage") or {}
    modelo = cuerpo["model"]
    _registrar(
        servicio, modelo, time.time() - t0, usd_tokens(modelo, uso),
        entrada=uso.get("input_tokens", 0),
        en_cache=(uso.get("input_tokens_details") or {}).get("cached_tokens", 0),
        salida=uso.get("output_tokens", 0),
        razonamiento=(uso.get("output_tokens_details") or {}).get("reasoning_tokens", 0),
    )
    return datos


def contar_tokens(cuerpo: dict) -> int:
    """POST /v1/responses/input_tokens: cuenta sin generar (no se cobra)."""
    r = _pedir("POST", "/responses/input_tokens", json=cuerpo)
    if r.status_code != 200:
        raise _error(r)
    return r.json()["input_tokens"]


def texto_de(respuesta: dict) -> str:
    partes = []
    for item in respuesta.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    partes.append(c.get("text", ""))
    return "".join(partes)


def subir_archivo(ruta: Path, segundos_vida: int = 3600) -> str:
    """Files API con caducidad: lo subido se borra solo aunque algo falle."""
    with ruta.open("rb") as f:
        r = _pedir(
            "POST", "/files",
            data={
                "purpose": "user_data",
                "expires_after[anchor]": "created_at",
                "expires_after[seconds]": str(segundos_vida),
            },
            files={"file": (ruta.name, f, "video/mp4" if ruta.suffix == ".mp4" else None)},
        )
    if r.status_code != 200:
        raise _error(r)
    # Quien suba debe llamar borrar_archivo al terminar; la caducidad es la red.
    return r.json()["id"]


def borrar_archivo(file_id: str) -> None:
    _pedir("DELETE", f"/files/{file_id}", intentos=2)


def transcribir_wav(ruta: Path, modo: str = "ENDPOINTING", idiomas=("Spanish",)) -> dict:
    """POST /v1/asr/transcribe con WAV mono 16 bits a 24 kHz (máx. 10 min, 32 MB)."""
    _revisar_tope()
    modelo = "muse-voice-transcribe-1.0"
    ajustes = {
        "mode": modo,
        "model": modelo,
        "audioEncoding": "WAV",
        "languageBias": list(idiomas),
    }
    t0 = time.time()
    with ruta.open("rb") as f:
        r = _pedir(
            "POST", "/asr/transcribe",
            files={
                "request": (None, json.dumps(ajustes), "application/json"),
                "audio": (ruta.name, f, "audio/wav"),
            },
        )
    if r.status_code != 200:
        raise _error(r)
    datos = r.json()
    horas = datos.get("audioDurationMs", 0) / 3_600_000
    _registrar("transcribir", modelo, time.time() - t0, horas * PRECIO_HORA_AUDIO[modelo],
               audio_ms=datos.get("audioDurationMs", 0))
    return datos
