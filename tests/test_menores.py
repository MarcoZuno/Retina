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


if __name__ == "__main__":
    unittest.main()
