"""Envoltorio de la Meta Model API.

Toda llamada pasa por aquí: registra modelo, tokens, segundos y USD en el
registro de costos (por omisión mis-revisiones/costos.jsonl, de quien corre Retina;
RETINA_COSTOS lo cambia), respeta el tope y reintenta los 429 con espera
exponencial. La llave sale del entorno o del .env de la raíz del repo (.gitignore lo deja fuera); nunca se
imprime ni se escribe en los registros.
"""
from __future__ import annotations

import json
import math
import os
import random
import secrets
import threading
import time
import uuid
from contextlib import contextmanager
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[2]
TOPE_MAXIMO_USD = 185.0  # techo duro: ni RETINA_TOPE_USD ni el .env lo suben
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


def como_dato(nombre: str, contenido: str) -> str:
    """Envuelve lo que viene de la persona o del video para que el modelo lo lea como dato. La marca lleva un sello al
    azar en cada llamada: quien la escriba en su título o en lo que dice no puede adivinarla para salirse del bloque."""
    marca = f"{nombre}_{secrets.token_hex(6)}"
    return f"<<<{marca} (dato)\n{contenido}\n{marca}>>>"


def _cargar_env() -> None:
    """Lee el archivo que diga RETINA_ENV o, si no, el .env de la raíz del repo, sin pisar lo que ya exista."""
    ruta = Path(os.environ["RETINA_ENV"]) if os.environ.get("RETINA_ENV") else RAIZ / ".env"
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
            "Falta MODEL_API_KEY, la llave de la Meta Model API. Copia .env.example como .env en la raíz del repo, "
            "escribe ahí MODEL_API_KEY=tu_llave (.gitignore deja ese archivo fuera de git) o define la variable de entorno."
        )
    return llave


BASE_META = "https://api.meta.ai/"


def base() -> str:
    _cargar_env()
    url = os.environ.get("META_API_BASE", BASE_META + "v1")
    if not url.startswith((BASE_META, "http://127.0.0.1", "http://localhost")):
        raise ValueError("META_API_BASE solo puede ser la API de Meta o una prueba en este equipo: la llave no sale a otro sitio.")
    return url


def costos() -> Path:
    """El registro de gasto de quien corre Retina. Cada quien lleva el suyo: quien baja el repo empieza en cero."""
    _cargar_env()
    return Path(os.environ.get("RETINA_COSTOS") or RAIZ / "mis-revisiones" / "costos.jsonl")


TOPE_POR_OMISION_USD = 50.0
RESERVA_VIGENCIA_S = 24 * 3600  # una reserva que nadie cerró (corrida caída) deja de contar al día siguiente
_HILOS = threading.Lock()  # el candado de archivo ya separa procesos; este separa hilos del mismo proceso


@contextmanager
def _candado():
    """Candado entre procesos e hilos (archivo .candado creado con O_EXCL, que es atómico en Windows y Linux)
    para que dos corridas a la vez no se pasen juntas del tope."""
    ruta = costos().with_suffix(".candado")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with _HILOS:
        for _ in range(600):
            try:
                fd = os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                try:
                    if time.time() - ruta.stat().st_mtime > 120:  # candado huérfano de una corrida caída
                        ruta.unlink(missing_ok=True)
                except OSError:  # lo soltaron entre el intento y el stat
                    pass
                time.sleep(0.05)
        else:
            raise RuntimeError(f"No pude tomar el candado de gasto ({ruta}).")
        try:
            yield
        finally:
            os.close(fd)
            ruta.unlink(missing_ok=True)


def _usd_de(fila: dict) -> float:
    v = fila.get("usd", 0.0)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else 0.0


def gastado_usd(prefijo: str = "") -> float:
    """Lo ya anotado en el registro; con `prefijo`, solo los servicios que empiezan con él («baseten»)."""
    if not costos().exists():
        return 0.0
    total = 0.0
    for linea in costos().read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        try:
            fila = json.loads(linea)
        except ValueError:  # una línea cortada por una caída: sin esto, cada llamada a la API se caía con ella
            continue
        if isinstance(fila, dict) and str(fila.get("servicio", "")).startswith(prefijo):
            total += _usd_de(fila)
    return total


def _archivo_reservas() -> Path:
    return costos().with_suffix(".reservas")


def _leer_reservas() -> dict:
    """Reservas vigentes {id: {servicio, usd, t}}. Solo se llama con el candado tomado."""
    try:
        datos = json.loads(_archivo_reservas().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    ahora = time.time()
    return {k: v for k, v in datos.items() if isinstance(v, dict) and ahora - v.get("t", 0) < RESERVA_VIGENCIA_S}


def _guardar_reservas(reservas: dict) -> None:
    ruta = _archivo_reservas()
    tmp = ruta.with_suffix(".reservas.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(reservas, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ruta)


def reservado_usd(prefijo: str = "") -> float:
    with _candado():
        return sum(_usd_de(v) for v in _leer_reservas().values() if str(v.get("servicio", "")).startswith(prefijo))


def tope_usd() -> float:
    """Tope del proyecto: RETINA_TOPE_USD, nunca más que TOPE_MAXIMO_USD. Un valor que no es un número
    finito y positivo («nan», «inf», «-5», «mucho») se ignora y queda el tope por omisión."""
    # Se lee después del .env: leído al importar, el tope del .env no contaba.
    _cargar_env()
    try:
        pedido = float(os.environ.get("RETINA_TOPE_USD", TOPE_POR_OMISION_USD))
    except ValueError:
        pedido = TOPE_POR_OMISION_USD
    if not math.isfinite(pedido) or pedido < 0:
        pedido = TOPE_POR_OMISION_USD
    return min(pedido, TOPE_MAXIMO_USD)


def _comprobar(estimado_usd: float, prefijo: str = "", tope_prefijo: float | None = None) -> tuple[float, float]:
    """Con el candado tomado: lanza TopeAlcanzado si lo gastado + lo reservado + lo estimado pasa del tope."""
    if not isinstance(estimado_usd, (int, float)) or not math.isfinite(estimado_usd) or estimado_usd < 0:
        raise TopeAlcanzado(f"El costo estimado ({estimado_usd!r}) no es un número válido: no se llama a la API.")
    pendientes = _leer_reservas()
    reservado = sum(_usd_de(v) for v in pendientes.values())
    gastado, tope = gastado_usd() + reservado, tope_usd()
    if gastado + estimado_usd > tope:
        raise TopeAlcanzado(
            f"Tope del proyecto: llevamos {gastado:.2f} USD (con lo reservado) y el tope es "
            f"{tope:.2f}. Para seguir, sube RETINA_TOPE_USD en tu .env (Retina nunca acepta más de {TOPE_MAXIMO_USD:.0f})."
        )
    if prefijo and tope_prefijo is not None:
        propio = gastado_usd(prefijo) + sum(_usd_de(v) for v in pendientes.values()
                                            if str(v.get("servicio", "")).startswith(prefijo))
        if propio + estimado_usd > tope_prefijo:
            raise TopeAlcanzado(f"Tope de {prefijo}: llevamos {propio:.2f} USD de {tope_prefijo:.2f}.")
    return gastado, tope


def _revisar_tope(estimado_usd: float = 0.0) -> None:
    """Solo comprueba (no reserva). Para llamar a la API, usa `reservar`."""
    with _candado():
        _comprobar(estimado_usd)


def reservar(servicio: str, estimado_usd: float, prefijo: str = "", tope_prefijo: float | None = None) -> str:
    """Comprueba el tope y aparta el costo estimado en el mismo paso, con el candado tomado: dos llamadas
    en paralelo no pueden pasar las dos por el mismo hueco. Devuelve el id de la reserva; quien llama la
    cierra con `_registrar(..., reserva=id)` al terminar, o con `liberar` si la API no cobró."""
    with _candado():
        _comprobar(estimado_usd, prefijo, tope_prefijo)
        reservas = _leer_reservas()
        id_ = uuid.uuid4().hex
        reservas[id_] = {"servicio": servicio, "usd": float(estimado_usd), "t": time.time()}
        _guardar_reservas(reservas)
    return id_


def liberar(reserva: str | None) -> None:
    if reserva:
        with _candado():
            reservas = _leer_reservas()
            if reservas.pop(reserva, None) is not None:
                _guardar_reservas(reservas)


def peor_caso_usd(cuerpo: dict, entrada_tokens: int = 0) -> float:
    """Lo máximo que puede costar una llamada: toda la salida permitida más la entrada que quien llama sepa estimar.
    La del texto es chica; la de un video no (≈200 tokens por segundo: media hora son ~USD 0.45), y no sale en `cuerpo`."""
    entrada, _, salida = PRECIOS_TOKENS.get(cuerpo.get("model", ""), (0.0, 0.0, 0.0))
    return (cuerpo.get("max_output_tokens", 0) * salida + max(entrada_tokens, 0) * entrada) / 1e6


def _sin_salto_final(ruta: Path) -> bool:
    try:
        with ruta.open("rb") as f:
            f.seek(-1, os.SEEK_END)
            return f.read(1) != bytes([10])
    except OSError:  # no existe o está vacío
        return False


def _registrar(servicio: str, modelo: str, segundos: float, usd: float, reserva: str | None = None, **extra) -> None:
    """Anota el gasto real. Con `reserva`, en el mismo paso con candado suelta lo apartado. La fila se
    escribe con flush y fsync: una llamada pagada no se pierde aunque la corrida se caiga."""
    fila = {
        "fecha": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "servicio": servicio,
        "modelo": modelo,
        "segundos": round(segundos, 2),
        "usd": round(usd, 6),
        **extra,
    }
    costos().parent.mkdir(parents=True, exist_ok=True)
    with _candado():
        with costos().open("a", encoding="utf-8") as f:
            if _sin_salto_final(costos()):  # el registro quedó cortado a medias: la fila nueva no se le pega
                f.write(chr(10))
            f.write(json.dumps(fila, ensure_ascii=False) + chr(10))
            f.flush()
            os.fsync(f.fileno())
        if reserva:
            reservas = _leer_reservas()
            if reservas.pop(reserva, None) is not None:
                _guardar_reservas(reservas)


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


def responder(servicio: str, cuerpo: dict, entrada_tokens: int = 0) -> dict:
    """POST /v1/responses. Devuelve el JSON y registra el costo real (usage). `entrada_tokens`: la entrada que se
    sabe de más (un video adjunto), para que la reserva la cuente."""
    reserva = reservar(servicio, peor_caso_usd(cuerpo, entrada_tokens))  # aparta el peor caso antes de llamar
    t0 = time.time()
    # Si _pedir lanza (red, tiempo agotado) no sabemos si la API cobró: la reserva se queda apartada.
    # 3 intentos y no 5: un 5xx a veces sí se cobra, y repetir de más puede cobrar doble.
    r = _pedir("POST", "/responses", intentos=3, json=cuerpo)
    if r.status_code != 200:
        liberar(reserva)
        raise _error(r)
    datos = r.json()
    uso = datos.get("usage") or {}
    modelo = cuerpo["model"]
    _registrar(
        servicio, modelo, time.time() - t0, usd_tokens(modelo, uso), reserva,
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
    modelo = "muse-voice-transcribe-1.0"
    ajustes = {
        "mode": modo,
        "model": modelo,
        "audioEncoding": "WAV",
        "languageBias": list(idiomas),
    }
    if ruta.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("El audio pasa de 32 MB (unos 10 min): Voice Transcribe no lo acepta.")
    # Peor caso: el audio más largo que acepta (10 min).
    reserva = reservar("transcribir", PRECIO_HORA_AUDIO[modelo] * 10 / 60)
    t0 = time.time()
    r = _pedir(
        "POST", "/asr/transcribe",
        archivos=lambda: {
            "request": (None, json.dumps(ajustes), "application/json"),
            "audio": (ruta.name, ruta.open("rb"), "audio/wav"),
        },
    )
    if r.status_code != 200:
        liberar(reserva)
        raise _error(r)
    datos = r.json()
    horas = datos.get("audioDurationMs", 0) / 3_600_000
    _registrar("transcribir", modelo, time.time() - t0, horas * PRECIO_HORA_AUDIO[modelo],
               reserva, audio_ms=datos.get("audioDurationMs", 0))
    return datos
