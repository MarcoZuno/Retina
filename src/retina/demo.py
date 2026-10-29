"""Demo sin llave ni GPU: abre el panel de Retina con un caso ya procesado.

Sirve la carpeta del repo solo en este equipo (127.0.0.1) y abre el navegador en el
panel. Por omisión muestra el ejemplo de casos/demo/; con --caso, cualquier
resultado.json que esté dentro del repo.

Con --casos CARPETA, los casos salen de una carpeta fuera del repo (por ejemplo, casos
reales que no se publican) y, si trae indice.json, --galeria abre la lista de todos.

Uso (desde la raíz del repo):
    python -m retina.demo [--caso casos/demo/resultado.json] [--puerto 8765] [--sin-navegador]
    python -m retina.demo --casos CARPETA --galeria
"""
from __future__ import annotations

import argparse
import functools
import http.server
import re
import webbrowser
from pathlib import Path

from .esquemas import RAIZ

CASO = re.compile(r"^/casos/[\w-]+/resultado\.json$")
PERMITIDO = re.compile(r"^/(panel/(index\.html|galeria\.html)?|panel/fondos/(?:fondo|mini)-[a-z]+\.webp"
                       r"|casos/[\w-]+/resultado\.json|casos/indice\.json"
                       r"|casos/[\w-]+/[\w-]+-ilustracion-ia\.(?:png|webp))$")  # el storyboard dibujado con Muse Image


def ruta_local(ruta: str, raiz: Path, casos: Path | None) -> Path | None:
    """El archivo que corresponde a una ruta permitida (None si no lo es). Con `casos`, lo de /casos/ sale de ahí."""
    if not PERMITIDO.match(ruta):
        return None
    partes = ruta.strip("/").split("/")
    if casos is not None and partes[0] == "casos":
        return casos.joinpath(*partes[1:])
    return raiz.joinpath(*partes)


class SoloElPanel(http.server.SimpleHTTPRequestHandler):
    """Sirve solo el panel (con sus fondos y la galería) y los casos; nada más del repo (ni .git ni .env)."""

    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".webp": "image/webp"}
    casos: Path | None = None

    def do_GET(self):  # noqa: N802 - nombre que pide http.server
        host = (self.headers.get("Host") or "").split(":")[0]
        ruta = self.path.split("?", 1)[0]
        if host not in ("127.0.0.1", "localhost") or not PERMITIDO.match(ruta):
            self.send_error(404)
            return
        super().do_GET()

    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    def translate_path(self, path):
        local = ruta_local(path.split("?", 1)[0], Path(self.directory), self.casos)
        return str(local) if local else str(Path(self.directory) / "no-existe")

    def list_directory(self, path):
        self.send_error(404)
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--caso", default="casos/demo/resultado.json", help="Ruta dentro del repo a un resultado.json.")
    ap.add_argument("--casos", type=Path, help="Carpeta de casos fuera del repo (cada uno en su carpeta, más indice.json).")
    ap.add_argument("--galeria", action="store_true", help="Abre la lista de todos los casos (necesita indice.json).")
    ap.add_argument("--puerto", type=int, default=8765)
    ap.add_argument("--sin-navegador", action="store_true")
    a = ap.parse_args()
    casos = a.casos.resolve() if a.casos else None
    if casos is not None and not casos.is_dir():
        raise SystemExit(f"No encuentro la carpeta de casos {a.casos}.")
    if a.galeria:
        if not ((casos or RAIZ / "casos") / "indice.json").is_file():
            raise SystemExit("La galería necesita un indice.json en la carpeta de casos.")
        destino = "/panel/galeria.html"
    else:
        caso = (RAIZ / a.caso).resolve()
        relativo = "/" + caso.relative_to(RAIZ.resolve()).as_posix() if RAIZ.resolve() in caso.parents else ""
        if not caso.is_file() or not CASO.match(relativo):
            raise SystemExit(f"No encuentro {a.caso}: tiene que ser casos/<carpeta>/resultado.json dentro del repo.")
        destino = f"/panel/?caso={relativo}"
    manejador = functools.partial(type("Manejador", (SoloElPanel,), {"casos": casos}), directory=str(RAIZ))
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", a.puerto), manejador)
    url = f"http://127.0.0.1:{servidor.server_port}{destino}"
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
