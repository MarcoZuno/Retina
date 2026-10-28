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
import webbrowser
from pathlib import Path

from .esquemas import RAIZ


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--caso", default="casos/demo/resultado.json", help="Ruta dentro del repo a un resultado.json.")
    ap.add_argument("--puerto", type=int, default=8765)
    ap.add_argument("--sin-navegador", action="store_true")
    a = ap.parse_args()
    caso = (RAIZ / a.caso).resolve()
    if RAIZ.resolve() not in caso.parents or not caso.is_file():
        raise SystemExit(f"No encuentro {a.caso} dentro del repo.")
    manejador = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(RAIZ))
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", a.puerto), manejador)
    url = f"http://127.0.0.1:{servidor.server_port}/panel/?caso=/{caso.relative_to(RAIZ.resolve()).as_posix()}"
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
