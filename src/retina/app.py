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


def leer_datos(cabeceras) -> dict:
    """Los datos del video vienen en cabeceras X-Retina-* (codificadas como URL por los acentos)."""
    def campo(nombre: str) -> str:
        return unquote(cabeceras.get(f"X-Retina-{nombre}") or "").strip()
    titulo, talento, codigo, fecha = campo("Titulo"), campo("Talento"), campo("Codigo").upper(), campo("Fecha")
    if not titulo or len(titulo) > 300:
        raise ValueError("Escribe el título del video (300 caracteres como máximo).")
    if len(talento) > 80:
        raise ValueError("El nombre del talento es demasiado largo.")
    if codigo and not CODIGO.match(codigo):  # opcional: un video de otra cuenta no tiene código
        raise ValueError("El código de producción tiene que verse como XYZ0000001: letras y luego números.")
    try:
        fecha = datetime.strptime(fecha, "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M")
    except ValueError:
        raise ValueError("La fecha de publicación tiene que traer día y hora.") from None
    return {"titulo": titulo, "talento": talento, "codigo": codigo, "fecha": fecha,
            "publicado": campo("Publicado") == "1", "idioma": "en" if campo("Idioma") == "en" else "es"}


def comparar_con(cabeceras, casos: Path) -> Path | None:
    """La carpeta de la versión A con la que se compara esta subida, o None si no viene la cabecera.
    Tiene que ser una revisión subida a este mismo servidor: un id de 12 letras hexadecimales cuya
    carpeta está en --casos y trae su video."""
    valor = cabeceras.get("X-Retina-Comparar-Con") or ""
    if not valor:
        return None
    if not ID.fullmatch(valor) or not any((casos / valor / n).is_file() for n in ("video.mp4", SUBIDA)):
        raise ValueError("No encuentro la versión A para comparar en este equipo. Vuelve a subir las dos versiones.")
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
    from .segmentar import _ffmpeg
    temporal = destino.with_name("convirtiendo.mp4")
    r = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(origen),
                        "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(temporal)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not temporal.is_file():
        temporal.unlink(missing_ok=True)
        raise ValueError("No pude leer ese video. Prueba exportarlo como MP4 y súbelo otra vez.")
    os.replace(temporal, destino)


_DIBUJANDO = threading.Lock()


def dibujar(carpeta: Path) -> tuple[int, dict]:
    """El storyboard del cambio con Muse Image, solo cuando la persona aprieta el botón (cuesta unos
    USD 0.03). Una vez dibujado, no se vuelve a pagar: se regresan las mismas imágenes."""
    ruta = carpeta / "resultado.json"
    if not ruta.is_file():
        return 404, {"error": "No encuentro esa revisión."}
    e = json.loads(ruta.read_text(encoding="utf-8")).get("explicacion") or {}
    if e.get("storyboard_imagenes"):
        return 200, {"imagenes": e["storyboard_imagenes"]}
    if not e.get("storyboard"):
        return 400, {"error": "Esta tarjeta no trae un cambio que dibujar."}
    if not _DIBUJANDO.acquire(blocking=False):
        return 409, {"error": "Ya se está dibujando otro storyboard. Espera un momento."}
    try:
        from .storyboard import generar
        rutas = generar(ruta, [], aprobar=True)
    except Exception as x:  # noqa: BLE001 — se le dice a la persona; el tope de gasto también cae aquí
        return 502, {"error": f"Muse Image no pudo dibujarlo ({type(x).__name__})."}
    finally:
        _DIBUJANDO.release()
    return 200, {"imagenes": [p.name for p in rutas]}


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
    except ValueError as e:  # el candado y los datos que no cuadran se le explican a la persona
        _escribir_estado(carpeta, estado="error", mensaje=str(e))
        return
    except Exception as e:  # noqa: BLE001 — cualquier otra falla se anota sin detalles internos
        (carpeta / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        _escribir_estado(carpeta, estado="error", mensaje=f"La revisión no terminó ({type(e).__name__}). Avisa a quien corre Retina.")
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
            m = re.match(r"^/api/estado/([0-9a-f]{12})$", ruta)
            if m and (self.casos / m.group(1)).is_dir():
                return self._json(200, estado(self.casos / m.group(1)))
            return self.send_error(404)
        return super().do_GET()

    def do_POST(self):  # noqa: N802
        m = re.match(r"^/api/storyboard/([0-9a-f]{12})$", self.path)
        if m and self._local() and pedido_propio(self.headers, self.server.server_port):
            return self._json(*dibujar(self.casos / m.group(1)))
        if self.path != "/api/revisar" or not self._local() or not pedido_propio(self.headers, self.server.server_port):
            return self.send_error(404)
        try:
            datos = leer_datos(self.headers)
            version_a = comparar_con(self.headers, self.casos)
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        largo = largo_valido(self.headers.get("Content-Length"))
        if largo is None or not 12 <= largo <= MAX_MB * 1024 * 1024:
            return self._json(400, {"error": f"El video tiene que pesar menos de {MAX_MB} MB."})
        cabeza = self.rfile.read(12)
        tipo = tipo_de_video(cabeza)
        if tipo is None:
            return self._json(400, {"error": "Eso no parece un video. Sube un MP4, MOV, WebM, MKV o AVI."})
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
            return self._json(400, {"error": "El video no llegó completo. Vuelve a intentarlo."})
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
    for ruta in (a.modelo, a.arranque, a.voz):
        if ruta is not None and not ruta.is_file():
            raise SystemExit(f"No encuentro {ruta}.")
    a.casos.mkdir(parents=True, exist_ok=True)
    from . import meta_api
    from .publico import cargar_modelo
    meta_api._cargar_env()  # FFMPEG y RETINA_* del .env: el orquestador los necesita antes de la primera llamada
    talentos = sorted({f["talento"] for f in cargar_modelo(a.modelo).filas if f.get("talento")})
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
