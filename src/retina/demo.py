"""Demo sin llave ni GPU: abre el panel de Retina con un caso ya procesado.

Sirve la carpeta del repo solo en este equipo (127.0.0.1) y abre el navegador en el
panel. Por omisión el panel elige el ejemplo por idioma (casos/demo o casos/demo-en); con --caso, cualquier
resultado.json que esté dentro del repo.

Con --casos CARPETA, los casos salen de una carpeta fuera del repo (por ejemplo, casos
reales que no se publican).

Uso (desde la raíz del repo):
    python -m retina.demo [--caso casos/demo/resultado.json] [--puerto 8765] [--sin-navegador]
"""
from __future__ import annotations

import argparse
import functools
import http.server
import re
import webbrowser
from pathlib import Path

from .esquemas import RAIZ

class ServidorExclusivo(http.server.ThreadingHTTPServer):
    """En Windows SO_REUSEADDR deja que dos servidores tomen el mismo puerto y el pedido cae en el equivocado:
    aquí un puerto ocupado es un error, no un permiso."""
    allow_reuse_address = False
    request_queue_size = 128  # la cola de 5 de http.server rechazaba ráfagas de cargas del panel


CASO = re.compile(r"^/casos/[\w-]+/resultado\.json$")
PERMITIDO = re.compile(r"^/(panel/(index\.html)?|panel/fondos/(?:fondo|mini)-[a-z]+\.webp"
                       r"|casos/[\w-]+/(?:resultado|comparacion)\.json"  # comparacion.json: versión A contra B
                       r"|casos/[\w-]+/apertura-antes\.(?:jpg|webp)"  # el primer cuadro del borrador
                       r"|casos/[\w-]+/[\w-]+-ilustracion-ia\.(?:png|webp))$")  # lo dibujado con Muse Image


def ruta_local(ruta: str, raiz: Path, casos: Path | None) -> Path | None:
    """El archivo que corresponde a una ruta permitida (None si no lo es). Con `casos`, lo de /casos/ sale de ahí."""
    if not PERMITIDO.match(ruta):
        return None
    partes = ruta.strip("/").split("/")
    if casos is not None and partes[0] == "casos":
        return casos.joinpath(*partes[1:])
    return raiz.joinpath(*partes)


class SoloElPanel(http.server.SimpleHTTPRequestHandler):
    """Sirve solo el panel (con sus fondos) y los casos; nada más del repo (ni .git ni .env)."""

    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".webp": "image/webp"}
    casos: Path | None = None
    hosts = ("127.0.0.1", "localhost")  # en línea se suma el dominio de la demo
    server_version, sys_version = "Retina", ""  # sin versión de Python en las respuestas

    def do_GET(self):  # noqa: N802 - nombre que pide http.server
        host = (self.headers.get("Host") or "").split(":")[0]
        ruta = self.path.split("?", 1)[0]
        if ruta == "/api/salud" and host in self.hosts:
            # La demo no sube videos: el panel lo pregunta aquí y no deja errores en la consola.
            cuerpo = b'{"subir": false}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
            return
        if host not in self.hosts or not PERMITIDO.match(ruta):
            self.send_error(404)
            return
        super().do_GET()

    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    def end_headers(self):
        if self.path.split("?", 1)[0].endswith((".html", ".json", "/")):  # páginas y casos siempre frescos
            self.send_header("Cache-Control", "no-cache")
        # Ninguna otra página puede incrustar estas en un marco, y el navegador no adivina tipos.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def translate_path(self, path):
        local = ruta_local(path.split("?", 1)[0], Path(self.directory), self.casos)
        return str(local) if local else str(Path(self.directory) / "no-existe")

    def list_directory(self, path):
        self.send_error(404)
        return None


def destino(caso: str | None) -> str:
    """Sin caso explícito el panel elige el suyo por idioma (casos/demo o casos/demo-en); con uno, se abre ese."""
    if caso is None:
        return "/panel/"
    ruta = (RAIZ / caso).resolve()
    relativo = "/" + ruta.relative_to(RAIZ.resolve()).as_posix() if RAIZ.resolve() in ruta.parents else ""
    if not ruta.is_file() or not CASO.match(relativo):
        raise SystemExit(f"No encuentro {caso}: tiene que ser casos/<carpeta>/resultado.json dentro del repo.")
    return f"/panel/?caso={relativo}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--caso", default=None, help="Ruta dentro del repo a un resultado.json. Sin ella, el panel elige el ejemplo por idioma.")
    ap.add_argument("--casos", type=Path, help="Carpeta de casos fuera del repo (cada uno en su carpeta).")
    ap.add_argument("--puerto", type=int, default=8765)
    ap.add_argument("--sin-navegador", action="store_true")
    a = ap.parse_args()
    casos = a.casos.resolve() if a.casos else None
    if casos is not None and not casos.is_dir():
        raise SystemExit(f"No encuentro la carpeta de casos {a.casos}.")
    ruta = destino(a.caso)
    manejador = functools.partial(type("Manejador", (SoloElPanel,), {"casos": casos}), directory=str(RAIZ))
    servidor = ServidorExclusivo(("127.0.0.1", a.puerto), manejador)
    url = f"http://127.0.0.1:{servidor.server_port}{ruta}"
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
