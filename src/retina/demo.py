"""Demo sin llave ni GPU: abre el panel de Retina con un caso ya procesado.

Sirve la carpeta del repo solo en este equipo (127.0.0.1) y abre el navegador en el
panel. Por omisión muestra el ejemplo de casos/demo/; con --caso, cualquier
resultado.json que esté dentro del repo.

Uso (desde la raíz del repo):
    python -m retina.demo [--caso casos/demo/resultado.json] [--puerto 8765] [--sin-navegador]
"""
from __future__ import annotations

import argparse
import functools
import http.server
import re
import webbrowser

from .esquemas import RAIZ

PERMITIDO = re.compile(r"^/(panel/(index\.html)?|casos/[\w-]+/resultado\.json)$")


class SoloElPanel(http.server.SimpleHTTPRequestHandler):
    """Sirve solo el panel y los resultado.json de casos/; nada más del repo (ni .git ni .env)."""

    def do_GET(self):  # noqa: N802 - nombre que pide http.server
        host = (self.headers.get("Host") or "").split(":")[0]
        ruta = self.path.split("?", 1)[0]
        if host not in ("127.0.0.1", "localhost") or not PERMITIDO.match(ruta):
            self.send_error(404)
            return
        super().do_GET()

    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    def list_directory(self, path):
        self.send_error(404)
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--caso", default="casos/demo/resultado.json", help="Ruta dentro del repo a un resultado.json.")
    ap.add_argument("--puerto", type=int, default=8765)
    ap.add_argument("--sin-navegador", action="store_true")
    a = ap.parse_args()
    caso = (RAIZ / a.caso).resolve()
    relativo = "/" + caso.relative_to(RAIZ.resolve()).as_posix() if RAIZ.resolve() in caso.parents else ""
    if not caso.is_file() or not PERMITIDO.match(relativo):
        raise SystemExit(f"No encuentro {a.caso}: tiene que ser casos/<carpeta>/resultado.json dentro del repo.")
    manejador = functools.partial(SoloElPanel, directory=str(RAIZ))
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", a.puerto), manejador)
    url = f"http://127.0.0.1:{servidor.server_port}/panel/?caso={relativo}"
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
