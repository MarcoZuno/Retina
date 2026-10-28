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
from contextlib import contextmanager
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[2]
COSTOS = Path(os.environ.get("RETINA_COSTOS", RAIZ / "costos.jsonl"))
TOPE_MAXIMO_USD = 50.0  # subirlo es cambiar esto 
TIEMPO = (10, 300)  # conectar, leer (s): una llamada colgada no detiene la corrida 50 min

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


def base() -> str:
    _cargar_env()
    return os.environ.get("META_API_BASE", "https://api.meta.ai/v1")


@contextmanager
def _candado():
    """Candado de archivo para que dos corridas a la vez no se pasen juntas del tope."""
    ruta = COSTOS.with_suffix(".candado")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(600):
        try:
            fd = os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.time() - ruta.stat().st_mtime > 120:  # candado huérfano de una corrida caída
                ruta.unlink(missing_ok=True)
            time.sleep(0.1)
    else:
        raise RuntimeError(f"No pude tomar el candado de gasto ({ruta}).")
    try:
        yield
    finally:
        os.close(fd)
        ruta.unlink(missing_ok=True)


def gastado_usd() -> float:
    if not COSTOS.exists():
        return 0.0
    total = 0.0
    for linea in COSTOS.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            total += json.loads(linea).get("usd", 0.0)
    return total


def tope_usd() -> float:
    # Se lee después del .env: leído al importar, el tope del .env no contaba.
    _cargar_env()
    return min(float(os.environ.get("RETINA_TOPE_USD", "50")), TOPE_MAXIMO_USD)


def _revisar_tope(estimado_usd: float = 0.0) -> None:
    with _candado():
        gastado, tope = gastado_usd(), tope_usd()
    if gastado + estimado_usd > tope:
        raise TopeAlcanzado(
            f"Tope del proyecto: llevamos {gastado:.2f} USD y el tope es "
            f"{tope:.2f}. Súbelo en tu .env si hace falta."
        )


def peor_caso_usd(cuerpo: dict) -> float:
    """Lo máximo que puede costar una llamada: toda la salida permitida (la entrada es menor)."""
    _, _, salida = PRECIOS_TOKENS.get(cuerpo.get("model", ""), (0.0, 0.0, 0.0))
    return cuerpo.get("max_output_tokens", 0) * salida / 1e6


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
    with _candado(), COSTOS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(fila, ensure_ascii=False) + "\n")


def usd_tokens(modelo: str, uso: dict) -> float:
    entrada, cache, salida = PRECIOS_TOKENS.get(modelo, (0.0, 0.0, 0.0))
    en_cache = (uso.get("input_tokens_details") or {}).get("cached_tokens", 0) or 0
    sin_cache = max(uso.get("input_tokens", 0) - en_cache, 0)
    return (sin_cache * entrada + en_cache * cache + uso.get("output_tokens", 0) * salida) / 1e6


def _espera(r: requests.Response | None, intento: int) -> float:
    valor = r.headers.get("Retry-After") if r is not None else None
    if valor:
        try:
            return min(float(valor), 120)
        except ValueError:  # también puede venir como fecha HTTP
            try:
                return max(0.0, min(parsedate_to_datetime(valor).timestamp() - time.time(), 120))
            except (TypeError, ValueError):
                pass
    return min(60, 2 ** intento) + random.random()


def _pedir(metodo: str, ruta: str, intentos: int = 5, archivos=None, **kwargs) -> requests.Response:
    """Petición con reintentos para 429, 5xx y fallas de red.

    `archivos` es una función que abre los archivos de nuevo en cada intento: un
    archivo ya leído en el primer intento se mandaría vacío en el segundo.
    """
    cabeceras = kwargs.pop("headers", {})
    cabeceras["Authorization"] = f"Bearer {_llave()}"
    r = None
    for intento in range(intentos):
        abiertos = archivos() if archivos else None
        try:
            r = requests.request(metodo, f"{base()}{ruta}", headers=cabeceras, timeout=TIEMPO,
                                 files=abiertos, **kwargs)
            if r.status_code != 429 and r.status_code < 500:
                return r
        except (requests.ConnectionError, requests.Timeout):
            if intento == intentos - 1:
                raise
        finally:
            for f in (abiertos or {}).values():
                if isinstance(f, tuple) and len(f) > 1 and hasattr(f[1], "close"):
                    f[1].close()
        time.sleep(_espera(r, intento))
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
    _revisar_tope(peor_caso_usd(cuerpo))
    t0 = time.time()
    # 3 intentos y no 5: un 5xx a veces sí se cobra, y repetir de más puede cobrar doble.
    r = _pedir("POST", "/responses", intentos=3, json=cuerpo)
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
    r = _pedir(
        "POST", "/files",
        data={
            "purpose": "user_data",
            "expires_after[anchor]": "created_at",
            "expires_after[seconds]": str(segundos_vida),
        },
        archivos=lambda: {"file": (ruta.name, ruta.open("rb"), "video/mp4" if ruta.suffix == ".mp4" else None)},
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
    if ruta.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("El audio pasa de 32 MB (unos 10 min): Voice Transcribe no lo acepta.")
    t0 = time.time()
    r = _pedir(
        "POST", "/asr/transcribe",
        archivos=lambda: {
            "request": (None, json.dumps(ajustes), "application/json"),
            "audio": (ruta.name, ruta.open("rb"), "audio/wav"),
        },
    )
    if r.status_code != 200:
        raise _error(r)
    datos = r.json()
    horas = datos.get("audioDurationMs", 0) / 3_600_000
    _registrar("transcribir", modelo, time.time() - t0, horas * PRECIO_HORA_AUDIO[modelo],
               audio_ms=datos.get("audioDurationMs", 0))
    return datos
