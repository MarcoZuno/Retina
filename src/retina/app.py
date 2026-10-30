"""Retina para usar: sube un video y recibe la tarjeta (prototipo que corre en un solo equipo).

Sirve el panel en 127.0.0.1; ahí mismo se sube el video. El video y sus datos llegan por
POST /api/revisar; el mismo orquestador de siempre (retina.retina.correr) lo revisa en segundo
plano, de uno en uno, y el panel consulta GET /api/estado/<id> hasta que la tarjeta está lista.
Cada revisión queda en su propia carpeta dentro de --casos y el panel la abre igual que cualquier
otro caso. Necesita un modelo (el cerebro público del repo, modelos/retina-publico.json, o el
privado de la casa) y la llave de la API en el .env.

Dos versiones del mismo video: la B se sube con la cabecera X-Retina-Comparar-Con (el id de la A).
Al terminar su tarjeta, retina.comparar escribe comparacion.json en la carpeta de la B (cuál
arranca mejor, en opinión de Spark, juzgada en los dos órdenes) y solo entonces queda «listo».

Guardas: solo responde en este equipo; solo acepta pedidos de su propia página (cabecera X-Retina
y mismo origen); solo MP4 y hasta MAX_MB; los datos se validan; el candado de «solo publicados»
sigue igual que en la línea de comandos.

Uso (desde la raíz del repo):
    python -m retina.app            # cerebro público y revisiones en mis-revisiones/
    python -m retina.app --casos CARPETA --modelo PREDECIR.pkl --arranque ARRANQUE.json --voz VOZ.jsonl  # la casa
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
import traceback
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from .demo import SoloElPanel
from .esquemas import RAIZ

MAX_MB = 800
ID = re.compile(r"^[0-9a-f]{12}$")
CODIGO = re.compile(r"^[A-Z]{2,10}\d{2,12}$")
# El avance se lee de los archivos que va dejando el orquestador, en este orden.
PASOS = (("manifiesto.json", "cortando"), ("transcribir.json", "escuchando"), ("describir.json", "mirando"),
         ("agente.json", "escribiendo"))
# Dos versiones del mismo video: la B se sube con la cabecera X-Retina-Comparar-Con (el id de la A) y,
# al terminar su tarjeta, Retina compara cómo arrancan las dos (retina.comparar).
COMPARAR_CON = "comparar_con.txt"
PASO_COMPARAR = ("comparacion.json", "comparando")
# La A entró antes a la misma fila de un solo hilo: cuando corre la B, ya terminó. La espera solo cubre
# el caso raro de que no (por ejemplo, si el servidor se reinició a media revisión de la A).
ESPERA_A_S = 600

# Lo que ve la persona cuando algo falla, en el idioma del panel. Los detalles técnicos van a error.txt.
TEXTOS = {
    "es": {
        "falta_titulo": "Escribe el título del video (300 caracteres como máximo).",
        "talento_largo": "El nombre del talento es demasiado largo.",
        "codigo_malo": "El código de producción tiene que verse como XYZ0000001: letras y luego números.",
        "falta_fecha": "La fecha de publicación tiene que traer día y hora.",
        "sin_version_a": "No encuentro la versión A para comparar en este equipo. Vuelve a subir las dos versiones.",
        "muy_pesado": "El video tiene que pesar menos de {mb} MB.",
        "no_es_video": "Eso no parece un video. Sube un MP4, MOV, WebM, MKV o AVI.",
        "incompleto": "El video no llegó completo. Vuelve a intentarlo.",
        "no_lee": "No pude leer ese video. Prueba exportarlo como MP4 y súbelo otra vez.",
        "sin_imagen": "Ese archivo no trae imagen: Retina revisa videos.",
        "muy_largo": "El video dura más de media hora: Retina revisa videos de hasta 30 minutos.",
        "ffmpeg_lento": "Cortar el video tardó demasiado y se detuvo. Prueba con un archivo más ligero.",
        "sin_ffmpeg": "A este equipo le falta ffmpeg, y Retina lo necesita para cortar el video. Instálalo "
                      "(Windows: winget install Gyan.FFmpeg · Mac: brew install ffmpeg · Linux: apt install ffmpeg) "
                      "y vuelve a abrir Retina.",
        "sin_llave": "Falta la llave de la Meta Model API (MODEL_API_KEY en el archivo .env). Sin ella Retina no "
                     "puede ver ni oír el video.",
        "candado": "El candado está encendido: a la API de Meta solo van videos ya publicados. Marca «ya "
                   "publicado», o apágalo con RETINA_SOLO_PUBLICADOS=0 si el video es tuyo.",
        "falla": "La revisión no terminó ({tipo}). El detalle quedó en error.txt, en la carpeta de la revisión.",
        "apertura_falla": "No se pudo terminar la apertura ({tipo}). Intenta otra vez; el detalle quedó en error.txt.",
        "tope": "Se llegó al tope de gasto que pusiste en RETINA_TOPE_USD.",
    },
    "en": {
        "falta_titulo": "Type the video's title (300 characters at most).",
        "talento_largo": "The talent's name is too long.",
        "codigo_malo": "The production code must look like XYZ0000001: letters, then numbers.",
        "falta_fecha": "The publishing date needs a day and a time.",
        "sin_version_a": "I can't find version A to compare on this computer. Upload both versions again.",
        "muy_pesado": "The video must be smaller than {mb} MB.",
        "no_es_video": "That doesn't look like a video. Upload an MP4, MOV, WebM, MKV or AVI.",
        "incompleto": "The video didn't arrive complete. Try again.",
        "no_lee": "I couldn't read that video. Try exporting it as MP4 and upload it again.",
        "sin_imagen": "That file has no picture: Retina reviews videos.",
        "muy_largo": "The video is longer than half an hour: Retina reviews videos up to 30 minutes.",
        "ffmpeg_lento": "Cutting the video took too long and was stopped. Try a lighter file.",
        "sin_ffmpeg": "This computer is missing ffmpeg, which Retina needs to cut the video. Install it "
                      "(Windows: winget install Gyan.FFmpeg · Mac: brew install ffmpeg · Linux: apt install ffmpeg) "
                      "and open Retina again.",
        "sin_llave": "The Meta Model API key is missing (MODEL_API_KEY in the .env file). Without it Retina "
                     "can't watch or hear the video.",
        "candado": "The lock is on: only already-published videos go to Meta's API. Tick «already published», "
                   "or turn it off with RETINA_SOLO_PUBLICADOS=0 if the video is yours.",
        "falla": "The review didn't finish ({tipo}). The details are in error.txt, in the review's folder.",
        "apertura_falla": "The opening could not be finished ({tipo}). Try again; the details are in error.txt.",
        "tope": "You reached the spending limit you set in RETINA_TOPE_USD.",
    },
}


def texto(idioma: str, clave: str, **datos) -> str:
    return TEXTOS["en" if idioma == "en" else "es"][clave].format(**datos)


def salud() -> dict:
    """Lo que hace falta para revisar un video en este equipo (sin decir nunca la llave)."""
    from .segmentar import Aviso, _ffmpeg
    try:
        _ffmpeg()
        ffmpeg = True
    except Aviso:
        ffmpeg = False
    return {"ffmpeg": ffmpeg, "llave": bool(os.environ.get("MODEL_API_KEY", "").strip())}


def leer_datos(cabeceras) -> dict:
    """Los datos del video vienen en cabeceras X-Retina-* (codificadas como URL por los acentos)."""
    def campo(nombre: str) -> str:
        return unquote(cabeceras.get(f"X-Retina-{nombre}") or "").strip()
    titulo, talento, codigo, fecha = campo("Titulo"), campo("Talento"), campo("Codigo").upper(), campo("Fecha")
    idioma = "en" if campo("Idioma") == "en" else "es"
    if not titulo or len(titulo) > 300:
        raise ValueError(texto(idioma, "falta_titulo"))
    if len(talento) > 80:
        raise ValueError(texto(idioma, "talento_largo"))
    if codigo and not CODIGO.match(codigo):  # opcional: un video de otra cuenta no tiene código
        raise ValueError(texto(idioma, "codigo_malo"))
    try:
        fecha = datetime.strptime(fecha, "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M")
    except ValueError:
        raise ValueError(texto(idioma, "falta_fecha")) from None
    return {"titulo": titulo, "talento": talento, "codigo": codigo, "fecha": fecha,
            "publicado": campo("Publicado") == "1", "idioma": idioma}


def comparar_con(cabeceras, casos: Path, idioma: str = "es") -> Path | None:
    """La carpeta de la versión A con la que se compara esta subida, o None si no viene la cabecera.
    Tiene que ser una revisión subida a este mismo servidor: un id de 12 letras hexadecimales cuya
    carpeta está en --casos y trae su video."""
    valor = cabeceras.get("X-Retina-Comparar-Con") or ""
    if not valor:
        return None
    if not ID.fullmatch(valor) or not any((casos / valor / n).is_file() for n in ("video.mp4", SUBIDA)):
        raise ValueError(texto(idioma, "sin_version_a"))
    return casos / valor


def es_mp4(cabeza: bytes) -> bool:
    return len(cabeza) >= 12 and cabeza[4:8] == b"ftyp"


# Lo que sube cualquier persona: MP4 y MOV (cajas ISO) se revisan tal cual; WebM, MKV, AVI y FLV se pasan
# a MP4 antes de revisar. Se mira el contenido, no el nombre del archivo.
SUBIDA = "subida-original.video"
CAJAS_ISO = (b"ftyp", b"wide", b"free", b"mdat", b"moov", b"skip", b"pnot")


def tipo_de_video(cabeza: bytes) -> str | None:
    """«mp4» si se revisa tal cual, «convertir» si hay que pasarlo a MP4, None si no parece video."""
    if len(cabeza) < 12:
        return None
    if es_mp4(cabeza):
        return "mp4"
    if (cabeza[4:8] in CAJAS_ISO or cabeza[:4] == b"\x1aE\xdf\xa3"  # MOV viejo o WebM/MKV
            or (cabeza[:4] == b"RIFF" and cabeza[8:12] == b"AVI ") or cabeza[:3] == b"FLV"):
        return "convertir"
    return None


def convertir_a_mp4(origen: Path, destino: Path) -> None:
    """Pasa el video a MP4 (H.264 y AAC) para que todo lo demás trabaje igual que con un MP4."""
    from .segmentar import TIEMPO_MAXIMO_S, Aviso, _ffmpeg
    temporal = destino.with_name("convirtiendo.mp4")
    try:
        r = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(origen),
                            "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(temporal)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIEMPO_MAXIMO_S)
    except subprocess.TimeoutExpired:
        temporal.unlink(missing_ok=True)
        raise Aviso("ffmpeg_lento", "Convertir el video tardó demasiado.") from None
    if r.returncode != 0 or not temporal.is_file():
        temporal.unlink(missing_ok=True)
        raise Aviso("no_lee", "No pude leer ese video. Prueba exportarlo como MP4 y súbelo otra vez.")
    os.replace(temporal, destino)


# Lo que va pasando con cada apertura. Vive en memoria: si Retina se reinicia a media corrida, se puede pedir otra vez.
_APERTURAS: dict[str, dict] = {}
_PIDIENDO_APERTURA = threading.Lock()


def estado_apertura(carpeta: Path) -> dict:
    if e := _APERTURAS.get(carpeta.name):
        return e
    return {"estado": "listo" if (carpeta / "apertura.json").exists() else "sin_pedir"}


def pedir_apertura(carpeta: Path, fila, idioma: str) -> tuple[int, dict]:
    """La apertura solo corre cuando la persona aprieta el botón: cuesta unos centavos. Una vez hecha no se vuelve
    a pagar, y dos clics seguidos forman una sola."""
    if not (carpeta / "resultado.json").is_file():
        return 404, {"error": "No encuentro esa revisión."}
    with _PIDIENDO_APERTURA:
        e = estado_apertura(carpeta)
        if e["estado"] == "listo":
            return 200, e
        if e["estado"] in ("en_fila", "procesando"):
            return 202, e
        listo = salud()
        for falta in ("ffmpeg", "llave"):
            if not listo[falta]:
                return 503, {"error": texto(idioma, f"sin_{falta}")}
        _APERTURAS[carpeta.name] = {"estado": "en_fila"}
    fila.submit(arreglar, carpeta, idioma)
    return 202, {"estado": "en_fila"}


def arreglar(carpeta: Path, idioma: str) -> None:
    """Corre la apertura en la misma fila que las revisiones y deja el avance a la vista del panel."""
    from . import apertura, meta_api

    def avisar(paso: str, vuelta: int) -> None:
        _APERTURAS[carpeta.name] = {"estado": "procesando", "paso": paso, "vuelta": vuelta}

    avisar("escribiendo", 0)
    try:
        apertura.rehacer(carpeta, idioma, avisar)
    except meta_api.TopeAlcanzado:
        _APERTURAS[carpeta.name] = {"estado": "error", "mensaje": texto(idioma, "tope")}
    except Exception as e:  # noqa: BLE001 — se le dice a la persona; el detalle queda en error.txt
        (carpeta / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        _APERTURAS[carpeta.name] = {"estado": "error", "mensaje": texto(idioma, "apertura_falla", tipo=type(e).__name__)}
    else:
        _APERTURAS.pop(carpeta.name, None)


def pedido_propio(cabeceras, puerto: int) -> bool:
    """Otra página abierta en el navegador no puede mandar videos aquí: el pedido trae X-Retina
    (eso obliga al navegador a preguntar antes, y este servidor no lo permite) y, si trae origen, es este."""
    origen = cabeceras.get("Origin")
    propios = {f"http://127.0.0.1:{puerto}", f"http://localhost:{puerto}"}
    return cabeceras.get("X-Retina") == "1" and (origen is None or origen in propios)


def estado(carpeta: Path) -> dict:
    ruta = carpeta / "estado.json"
    if not ruta.exists():
        return {"estado": "en_fila"}
    e = json.loads(ruta.read_text(encoding="utf-8"))
    if e.get("estado") != "procesando":
        return e
    pasos = PASOS + ((PASO_COMPARAR,) if (carpeta / COMPARAR_CON).exists() else ())  # una sola versión: los de siempre
    paso = next((nombre for archivo, nombre in pasos if not (carpeta / archivo).exists()), "terminando")
    return {"estado": "procesando", "paso": paso}


def largo_valido(valor: str | None) -> int | None:
    """El Content-Length solo si es un entero positivo escrito con dígitos."""
    return int(valor) if valor and valor.isdigit() else None


def _escribir_estado(carpeta: Path, **e) -> None:
    """Se escribe a un temporal y se reemplaza de un golpe: quien lo lee nunca ve un archivo a medias."""
    temporal = carpeta / "estado.json.tmp"
    temporal.write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")
    os.replace(temporal, carpeta / "estado.json")


def revisar(carpeta: Path, datos: dict, modelos: dict, espera_s: float = ESPERA_A_S) -> None:
    """Corre el orquestador de punta a punta sobre el video subido (en segundo plano). Si es la versión B
    de una comparación, al terminar su tarjeta compara las dos antes de marcarla lista."""
    from .retina import correr
    _escribir_estado(carpeta, estado="procesando")
    try:
        if (carpeta / SUBIDA).is_file():  # WebM, MKV, AVI…: primero a MP4
            convertir_a_mp4(carpeta / SUBIDA, carpeta / "video.mp4")
            (carpeta / SUBIDA).unlink()
        correr(carpeta / "video.mp4", modelos["modelo"], carpeta, datos["codigo"], datos["talento"], datos["fecha"],
               datos["titulo"], True, modelos["arranque"], voz=modelos["voz"], publicado=datos["publicado"],
               idioma=datos.get("idioma", "es"))
        marca = carpeta / COMPARAR_CON
        if not marca.exists():
            _escribir_estado(carpeta, estado="listo")
            return
    except ValueError as e:  # el candado y los datos que no cuadran se le explican a la persona, en su idioma
        clave, idioma = getattr(e, "clave", None), datos.get("idioma", "es")
        _escribir_estado(carpeta, estado="error", mensaje=texto(idioma, clave) if clave in TEXTOS["es"] else str(e))
        return
    except Exception as e:  # noqa: BLE001 — cualquier otra falla se anota sin detalles internos
        (carpeta / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        _escribir_estado(carpeta, estado="error", mensaje=texto(datos.get("idioma", "es"), "falla", tipo=type(e).__name__))
        return
    comparar_al_terminar(carpeta, marca.read_text(encoding="utf-8").strip(), espera_s)


def comparar_al_terminar(carpeta: Path, id_a: str, espera_s: float = ESPERA_A_S, cada_s: float = 2.0) -> None:
    """La tarjeta de la B ya está. Espera a que la A esté lista y compara cómo arrancan las dos.
    Si la A falló, la B sale con error; si lo que falla es la comparación, la tarjeta de la B se queda
    y el estado lo dice en «comparacion_error»."""
    version_a = carpeta.parent / id_a
    if not ID.fullmatch(id_a) or not version_a.is_dir():
        _escribir_estado(carpeta, estado="listo", comparacion_error="No encontré la versión A para comparar; "
                         "la tarjeta de esta versión sí quedó.")
        return
    fin = time.monotonic() + espera_s
    while (e := estado(version_a))["estado"] not in ("listo", "error") and time.monotonic() < fin:
        time.sleep(max(0.0, min(cada_s, fin - time.monotonic())))
    if e["estado"] == "error":
        _escribir_estado(carpeta, estado="error", mensaje="La versión A no se pudo revisar, así que no se pudo comparar "
                         f"con esta. Lo que pasó con la versión A: {e.get('mensaje') or 'no hay detalle'}")
        return
    if e["estado"] != "listo":
        _escribir_estado(carpeta, estado="listo", comparacion_error="La versión A no terminó su revisión a tiempo y no "
                         "se pudo comparar; la tarjeta de esta versión sí quedó.")
        return
    from . import meta_api
    from .comparar import comparar
    try:
        comparar(version_a, carpeta)
    except meta_api.TopeAlcanzado:
        _escribir_estado(carpeta, estado="listo", comparacion_error="No se pudo comparar con la versión A: se llegó al "
                         "tope de gasto del proyecto. La tarjeta de esta versión sí quedó.")
        return
    except Exception as e:  # noqa: BLE001 — la tarjeta de la B no se pierde por la comparación
        (carpeta / "comparacion-error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        _escribir_estado(carpeta, estado="listo", comparacion_error=f"No se pudo comparar con la versión A "
                         f"({type(e).__name__}). La tarjeta de esta versión sí quedó.")
        return
    _escribir_estado(carpeta, estado="listo")


class ConSubida(SoloElPanel):
    """El panel, más la API para subir un video y seguir su revisión."""

    timeout = 60  # una conexión que deja de mandar datos se corta en vez de dejar un hilo colgado
    modelos: dict = {}
    fila: ThreadPoolExecutor | None = None
    talentos: list[str] = []

    def _json(self, codigo: int, cuerpo: dict) -> None:
        datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(datos)

    def _local(self) -> bool:
        return (self.headers.get("Host") or "").split(":")[0] in ("127.0.0.1", "localhost")

    def do_GET(self):  # noqa: N802
        ruta = self.path.split("?", 1)[0]
        if ruta.startswith("/api/"):
            if not self._local():
                return self.send_error(404)
            if ruta == "/api/talentos":
                return self._json(200, {"talentos": self.talentos})
            if ruta == "/api/salud":  # el panel avisa al abrir si falta algo, antes de que la persona suba nada
                return self._json(200, {"subir": True, **salud(), "cerebro": self.modelos.get("modelo") is not None})
            m = re.match(r"^/api/estado/([0-9a-f]{12})$", ruta)
            if m and (self.casos / m.group(1)).is_dir():
                return self._json(200, estado(self.casos / m.group(1)))
            m = re.match(r"^/api/apertura/([0-9a-f]{12})$", ruta)
            if m and (self.casos / m.group(1)).is_dir():
                return self._json(200, estado_apertura(self.casos / m.group(1)))
            return self.send_error(404)
        return super().do_GET()

    def do_POST(self):  # noqa: N802
        m = re.match(r"^/api/apertura/([0-9a-f]{12})$", self.path)
        if m and self._local() and pedido_propio(self.headers, self.server.server_port):
            idioma = "en" if unquote(self.headers.get("X-Retina-Idioma") or "") == "en" else "es"
            return self._json(*pedir_apertura(self.casos / m.group(1), self.fila, idioma))
        if self.path != "/api/revisar" or not self._local() or not pedido_propio(self.headers, self.server.server_port):
            return self.send_error(404)
        idioma = "en" if unquote(self.headers.get("X-Retina-Idioma") or "") == "en" else "es"
        try:
            datos = leer_datos(self.headers)
            version_a = comparar_con(self.headers, self.casos, idioma)
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        listo = salud()
        for falta in ("ffmpeg", "llave"):  # mejor decirlo ahora que después de subir 800 MB
            if not listo[falta]:
                return self._json(503, {"error": texto(idioma, f"sin_{falta}")})
        largo = largo_valido(self.headers.get("Content-Length"))
        if largo is None or not 12 <= largo <= MAX_MB * 1024 * 1024:
            return self._json(400, {"error": texto(idioma, "muy_pesado", mb=MAX_MB)})
        cabeza = self.rfile.read(12)
        tipo = tipo_de_video(cabeza)
        if tipo is None:
            return self._json(400, {"error": texto(idioma, "no_es_video")})
        id_ = secrets.token_hex(6)
        carpeta = self.casos / id_
        carpeta.mkdir()
        with (carpeta / ("video.mp4" if tipo == "mp4" else SUBIDA)).open("wb") as f:
            f.write(cabeza)
            falta = largo - len(cabeza)
            while falta > 0:
                trozo = self.rfile.read(min(1 << 20, falta))
                if not trozo:
                    break
                f.write(trozo)
                falta -= len(trozo)
        if falta > 0:
            shutil.rmtree(carpeta, ignore_errors=True)
            return self._json(400, {"error": texto(idioma, "incompleto")})
        if version_a is not None:  # antes de la fila: la revisión de la B ya sabe que va a comparar
            (carpeta / COMPARAR_CON).write_text(version_a.name, encoding="utf-8")
        self.fila.submit(revisar, carpeta, datos, self.modelos)
        return self._json(202, {"id": id_})

    def do_OPTIONS(self):  # noqa: N802 — sin permisos para otros sitios
        self.send_error(404)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--casos", type=Path, default=RAIZ / "mis-revisiones",
                    help="Carpeta donde queda cada revisión (fuera del repo: mis-revisiones/ está en .gitignore).")
    ap.add_argument("--modelo", type=Path, default=RAIZ / "modelos" / "retina-publico.json",
                    help="Por omisión, el cerebro público. Un .pkl es el modelo privado de una empresa.")
    ap.add_argument("--arranque", type=Path, help="Solo con el modelo privado; el público trae su riesgo.")
    ap.add_argument("--voz", type=Path, help="Transcripciones de la casa para el agente (privadas). Sin ellas, tarjeta de una vuelta.")
    ap.add_argument("--puerto", type=int, default=8790)
    ap.add_argument("--sin-navegador", action="store_true")
    a = ap.parse_args()
    if not a.modelo.is_file():
        print(f"Aviso: no encuentro {a.modelo}. Retina revisará los videos sin número (solo con los modelos de Meta).")
        a.modelo = None
    for ruta in (a.arranque, a.voz):
        if ruta is not None and not ruta.is_file():
            raise SystemExit(f"No encuentro {ruta}.")
    a.casos.mkdir(parents=True, exist_ok=True)
    from . import meta_api
    from .publico import cargar_modelo
    meta_api._cargar_env()  # FFMPEG y RETINA_* del .env: el orquestador los necesita antes de la primera llamada
    talentos = sorted({f["talento"] for f in cargar_modelo(a.modelo).filas if f.get("talento")}) if a.modelo else []
    listo = salud()
    if not listo["ffmpeg"]:
        print("Aviso: falta ffmpeg. Instálalo (Windows: winget install Gyan.FFmpeg · Mac: brew install ffmpeg · "
              "Linux: apt install ffmpeg) o pon su ruta en la variable FFMPEG. Sin él no se puede revisar ningún video.")
    if not listo["llave"]:
        print("Aviso: falta MODEL_API_KEY en el .env. Sin ella Retina no puede ver ni oír los videos.")
    clase = type("Manejador", (ConSubida,), {
        "casos": a.casos.resolve(), "talentos": talentos, "fila": ThreadPoolExecutor(max_workers=1),
        "modelos": {k: (r.resolve() if r else None) for k, r in (("modelo", a.modelo), ("arranque", a.arranque), ("voz", a.voz))}})
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", a.puerto), functools.partial(clase, directory=str(RAIZ)))
    url = f"http://127.0.0.1:{servidor.server_port}/panel/"
    print(f"Retina está en {url}  (Ctrl+C para cerrar)")
    if not a.sin_navegador:
        webbrowser.open(url)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
