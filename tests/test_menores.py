"""Fallas menores de la auditoría del 30-oct (B9 a B21 y D4): una prueba por falla, sin API ni red hacia fuera.
Corren con: python -m unittest discover -s tests   (desde la raíz del repo)
"""
from __future__ import annotations

import http.server
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

import json
import re
import tempfile
from unittest import mock

from retina import app, demo, meta_api, retina  # noqa: E402


class PuertoExclusivo(unittest.TestCase):
    """B9: en Windows SO_REUSEADDR deja que dos servidores tomen el mismo puerto y la revisión llega al equivocado."""

    def _dos(self, clase):
        uno = clase(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler)
        self.addCleanup(uno.server_close)
        otro = None
        try:
            otro = clase(("127.0.0.1", uno.server_port), http.server.BaseHTTPRequestHandler)
            self.addCleanup(otro.server_close)
        except OSError:
            pass
        return otro

    def test_el_servidor_de_la_demo_no_comparte_puerto(self):
        self.assertIsNone(self._dos(demo.ServidorExclusivo))

    def test_la_app_usa_el_mismo_servidor_exclusivo(self):
        self.assertIs(app.ServidorExclusivo, demo.ServidorExclusivo)


class TopeEnMedioDeLaRevision(unittest.TestCase):
    """B10: si el tope se alcanza a media revisión, la persona tiene que saberlo; no un «listo» con un paso que «falló»."""

    def test_paso_deja_pasar_el_tope(self):
        def gasta():
            raise meta_api.TopeAlcanzado("tope")
        with self.assertRaises(meta_api.TopeAlcanzado):
            retina._paso("x", {}, [], "algo", gasta)

    def test_paso_sigue_anotando_las_otras_fallas(self):
        no_pude = []
        self.assertIsNone(retina._paso("x", {}, no_pude, "algo", lambda: 1 / 0))
        self.assertEqual(len(no_pude), 1)

    def test_la_revision_termina_en_error_con_el_texto_del_tope(self):
        for idioma in ("es", "en"):
            with tempfile.TemporaryDirectory() as d, mock.patch.object(retina, "correr", side_effect=meta_api.TopeAlcanzado("x")):
                carpeta = Path(d)
                datos = {"codigo": "A", "talento": "", "fecha": "2026-01-01 10:00", "titulo": "t", "publicado": True, "idioma": idioma}
                app.revisar(carpeta, datos, {"modelo": None, "arranque": None, "voz": None})
                e = json.loads((carpeta / "estado.json").read_text(encoding="utf-8"))
                self.assertEqual((e["estado"], e["mensaje"]), ("error", app.texto(idioma, "tope")))
                self.assertFalse((carpeta / "error.txt").exists())  # no es una falla del programa: no hay traceback


class DemoEstaticaConNginx(unittest.TestCase):
    """B11: lo que el servidor de Python deja ver (demo.PERMITIDO), nginx también; si no, la demo estática sale sin imágenes."""

    def _regex_de_nginx(self) -> list:
        conf = (RAIZ / "deploy" / "nginx.conf").read_text(encoding="utf-8")
        return [re.compile(r) for r in re.findall(r"location ~ (\S+) \{", conf)]

    def test_cada_archivo_de_casos_que_el_panel_pide_lo_sirve_nginx(self):
        archivos = ["/casos/demo/" + p.name for p in (RAIZ / "casos" / "demo").iterdir()]
        archivos += ["/casos/abc-123/comparacion.json", "/casos/abc-123/apertura-antes.jpg", "/casos/abc-123/apertura-cuadro2-ilustracion-ia.png"]
        reglas = self._regex_de_nginx()
        for ruta in archivos:
            if demo.PERMITIDO.match(ruta):
                self.assertTrue(any(r.match(ruta) for r in reglas), f"nginx no sirve {ruta}")

    def test_nginx_no_abre_mas_que_el_servidor_de_python(self):
        reglas = self._regex_de_nginx()
        for ruta in ("/casos/demo/video.mp4", "/casos/demo/error.txt", "/casos/demo/estado.json", "/casos/../etc/passwd",
                     "/casos/demo/x-ilustracion-ia.svg"):
            self.assertFalse(any(r.match(ruta) for r in reglas), f"nginx sirve {ruta}")


if __name__ == "__main__":
    unittest.main()
