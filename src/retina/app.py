"""Retina para usar: sube un video y recibe la tarjeta (prototipo que corre en un solo equipo).

Sirve en 127.0.0.1 el panel, la galería y la página «subir». El video y sus datos llegan por
POST /api/revisar; el mismo orquestador de siempre (retina.retina.correr) lo revisa en segundo
plano, de uno en uno, y la página consulta GET /api/estado/<id> hasta que la tarjeta está lista.
Cada revisión queda en su propia carpeta dentro de --casos, así que la galería y el panel la abren
igual que cualquier otro caso. Necesita los modelos (privados) y la llave de la API en el .env.

Guardas: solo responde en este equipo; solo acepta pedidos de su propia página (cabecera X-Retina
y mismo origen); solo MP4 y hasta MAX_MB; los datos se validan; el candado de «solo publicados»
sigue igual que en la línea de comandos.

Uso (desde la raíz del repo):
    python -m retina.app --casos CARPETA --modelo PREDECIR.pkl --arranque ARRANQUE.json --voz VOZ.jsonl
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


def leer_datos(cabeceras) -> dict:
    """Los datos del video vienen en cabeceras X-Retina-* (codificadas como URL por los acentos)."""
    def campo(nombre: str) -> str:
        return unquote(cabeceras.get(f"X-Retina-{nombre}") or "").strip()
    titulo, talento, codigo, fecha = campo("Titulo"), campo("Talento"), campo("Codigo").upper(), campo("Fecha")
    if not titulo or len(titulo) > 300:
        raise ValueError("Escribe el título del video (300 caracteres como máximo).")
    if len(talento) > 80:
        raise ValueError("El nombre del talento es demasiado largo.")
    if not CODIGO.match(codigo):
        raise ValueError("El código de producción tiene que verse como XYZ0000001: letras y luego números.")
    try:
        fecha = datetime.strptime(fecha, "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M")
    except ValueError:
        raise ValueError("La fecha de publicación tiene que traer día y hora.") from None
    return {"titulo": titulo, "talento": talento, "codigo": codigo, "fecha": fecha,
            "publicado": campo("Publicado") == "1"}


def es_mp4(cabeza: bytes) -> bool:
    return len(cabeza) >= 12 and cabeza[4:8] == b"ftyp"


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
    paso = next((nombre for archivo, nombre in PASOS if not (carpeta / archivo).exists()), "terminando")
    return {"estado": "procesando", "paso": paso}


def largo_valido(valor: str | None) -> int | None:
    """El Content-Length solo si es un entero positivo escrito con dígitos."""
    return int(valor) if valor and valor.isdigit() else None


def _escribir_estado(carpeta: Path, **e) -> None:
    """Se escribe a un temporal y se reemplaza de un golpe: quien lo lee nunca ve un archivo a medias."""
    temporal = carpeta / "estado.json.tmp"
    temporal.write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")
    os.replace(temporal, carpeta / "estado.json")


def revisar(carpeta: Path, datos: dict, modelos: dict) -> None:
    """Corre el orquestador de punta a punta sobre el video subido (en segundo plano)."""
    from .retina import correr
    _escribir_estado(carpeta, estado="procesando")
    try:
        correr(carpeta / "video.mp4", modelos["modelo"], carpeta, datos["codigo"], datos["talento"], datos["fecha"],
               datos["titulo"], True, modelos["arranque"], voz=modelos["voz"], publicado=datos["publicado"])
        _escribir_estado(carpeta, estado="listo")
    except ValueError as e:  # el candado y los datos que no cuadran se le explican a la persona
        _escribir_estado(carpeta, estado="error", mensaje=str(e))
    except Exception as e:  # noqa: BLE001 — cualquier otra falla se anota sin detalles internos
        (carpeta / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        _escribir_estado(carpeta, estado="error", mensaje=f"La revisión no terminó ({type(e).__name__}). Avisa a quien corre Retina.")


class ConSubida(SoloElPanel):
    """El panel y la galería, más la API para subir un video y seguir su revisión."""

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
        if self.path != "/api/revisar" or not self._local() or not pedido_propio(self.headers, self.server.server_port):
            return self.send_error(404)
        try:
            datos = leer_datos(self.headers)
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        largo = largo_valido(self.headers.get("Content-Length"))
        if largo is None or not 12 <= largo <= MAX_MB * 1024 * 1024:
            return self._json(400, {"error": f"El video tiene que pesar menos de {MAX_MB} MB."})
        cabeza = self.rfile.read(12)
        if not es_mp4(cabeza):
            return self._json(400, {"error": "Solo se pueden revisar videos MP4."})
        id_ = secrets.token_hex(6)
        carpeta = self.casos / id_
        carpeta.mkdir()
        with (carpeta / "video.mp4").open("wb") as f:
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
        self.fila.submit(revisar, carpeta, datos, self.modelos)
        return self._json(202, {"id": id_})

    def do_OPTIONS(self):  # noqa: N802 — sin permisos para otros sitios
        self.send_error(404)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--casos", type=Path, required=True, help="Carpeta donde queda cada revisión (privada).")
    ap.add_argument("--modelo", type=Path, required=True)
    ap.add_argument("--arranque", type=Path, required=True)
    ap.add_argument("--voz", type=Path, required=True)
    ap.add_argument("--puerto", type=int, default=8790)
    ap.add_argument("--sin-navegador", action="store_true")
    a = ap.parse_args()
    for ruta in (a.modelo, a.arranque, a.voz):
        if not ruta.is_file():
            raise SystemExit(f"No encuentro {ruta}.")
    a.casos.mkdir(parents=True, exist_ok=True)
    from . import meta_api
    from .predecir import Modelo
    meta_api._cargar_env()  # FFMPEG y RETINA_* del .env: el orquestador los necesita antes de la primera llamada
    talentos = sorted({f["talento"] for f in Modelo.cargar(a.modelo).filas if f.get("talento")})
    clase = type("Manejador", (ConSubida,), {
        "casos": a.casos.resolve(), "talentos": talentos, "fila": ThreadPoolExecutor(max_workers=1),
        "modelos": {"modelo": a.modelo.resolve(), "arranque": a.arranque.resolve(), "voz": a.voz.resolve()}})
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", a.puerto), functools.partial(clase, directory=str(RAIZ)))
    url = f"http://127.0.0.1:{servidor.server_port}/panel/subir.html"
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
