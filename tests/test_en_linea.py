"""La demo en línea para jueces: código de acceso, tope de gasto, límites y borrado.

Sin API, sin llaves y sin red hacia fuera: un servidor local con la app. Corren con:
python -m unittest discover -s tests   (desde la raíz del repo)
"""
from __future__ import annotations

import functools
import http.client
import http.server
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from retina import app, segmentar  # noqa: E402

CODIGO = "codigo-de-los-jueces-2026"
SITIO = "https://retina.ejemplo.com"
ENTORNO = {"RETINA_CODIGO_ACCESO": CODIGO, "RETINA_SITIO": SITIO, "RETINA_TOPE_USD": "30"}


class Configuracion(unittest.TestCase):
    def test_con_todo_arranca(self):
        c = app.config_en_linea(ENTORNO)
        self.assertEqual((c["codigo"], c["sitio"], c["host"]), (CODIGO, SITIO, "retina.ejemplo.com"))

    def test_no_arranca_con_un_codigo_corto(self):
        with self.assertRaises(SystemExit):
            app.config_en_linea({**ENTORNO, "RETINA_CODIGO_ACCESO": "abc"})

    def test_no_arranca_sin_https(self):
        with self.assertRaises(SystemExit):
            app.config_en_linea({**ENTORNO, "RETINA_SITIO": "http://retina.ejemplo.com"})

    def test_no_arranca_con_un_tope_que_pase_de_30_dolares(self):
        for tope in ("31", "", "muchos", "inf", "-1"):
            with self.subTest(tope=tope), self.assertRaises(SystemExit):
                app.config_en_linea({**ENTORNO, "RETINA_TOPE_USD": tope})


class Acceso(unittest.TestCase):
    def test_solo_pasa_el_codigo_exacto(self):
        self.assertTrue(app.acceso_valido({"X-Retina-Acceso": CODIGO}, CODIGO))
        for malo in ({}, {"X-Retina-Acceso": ""}, {"X-Retina-Acceso": "otro"}, {"X-Retina-Acceso": CODIGO + "x"}):
            self.assertFalse(app.acceso_valido(malo, CODIGO), malo)

    def test_acepta_pedidos_de_su_sitio_y_de_ningun_otro(self):
        self.assertTrue(app.pedido_propio({"X-Retina": "1", "Origin": SITIO}, 8080, SITIO))
        self.assertFalse(app.pedido_propio({"X-Retina": "1", "Origin": "https://otro.com"}, 8080, SITIO))


class Limpieza(unittest.TestCase):
    def test_borra_lo_viejo_y_deja_lo_reciente(self):
        with tempfile.TemporaryDirectory() as d:
            casos = Path(d)
            viejo, nuevo, ajeno = casos / "a1b2c3d4e5f6", casos / "0f9e8d7c6b5a", casos / "no-es-un-caso"
            for x in (viejo, nuevo, ajeno):
                x.mkdir()
                (x / "video.mp4").write_bytes(b"x")
            hace_dos_dias = time.time() - 2 * 86400
            os.utime(viejo, (hace_dos_dias, hace_dos_dias))
            os.utime(ajeno, (hace_dos_dias, hace_dos_dias))
            app.limpiar(casos)
            self.assertEqual(sorted(p.name for p in casos.iterdir()), sorted([nuevo.name, ajeno.name]))


class Fila(unittest.TestCase):
    def test_cuenta_lo_que_falta_y_baja_al_terminar(self):
        fila, soltar, listo = app.FilaContada(), threading.Event(), threading.Event()
        fila.submit(soltar.wait)
        fila.submit(listo.set)
        self.assertEqual(fila.pendientes(), 2)
        soltar.set(); listo.wait(5)
        for _ in range(100):
            if fila.pendientes() == 0:
                break
            time.sleep(0.01)
        self.assertEqual(fila.pendientes(), 0)


class Duracion(unittest.TestCase):
    def test_en_linea_el_maximo_baja(self):
        with mock.patch.dict(os.environ, {"RETINA_DURACION_MAXIMA_S": "300"}):
            self.assertEqual(segmentar.maximo_s(), 300)

    def test_de_fabrica_sigue_en_30_minutos_y_un_valor_raro_no_lo_sube(self):
        with mock.patch.dict(os.environ, {"RETINA_DURACION_MAXIMA_S": ""}):
            self.assertEqual(segmentar.maximo_s(), 1800)
        with mock.patch.dict(os.environ, {"RETINA_DURACION_MAXIMA_S": "mucho"}):
            self.assertEqual(segmentar.maximo_s(), 1800)
        with mock.patch.dict(os.environ, {"RETINA_DURACION_MAXIMA_S": "99999"}):
            self.assertEqual(segmentar.maximo_s(), 1800)


class EnVivo(unittest.TestCase):
    """La app de verdad, detrás de un puerto local, como la dejaría el proxy."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.casos = Path(self.tmp.name)
        self.caso = self.casos / "a1b2c3d4e5f6"
        self.caso.mkdir()
        (self.caso / "resultado.json").write_text("{}", encoding="utf-8")
        self.fila = mock.Mock()
        self.fila.pendientes.return_value = 0
        clase = type("Manejador", (app.ConSubida,), {
            "casos": self.casos, "fila": self.fila, "talentos": [], "modelos": {"modelo": None, "arranque": None, "voz": None},
            "hosts": ("127.0.0.1", "localhost", "retina.ejemplo.com"), "en_linea": app.config_en_linea(ENTORNO)})
        self.servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(clase, directory=str(RAIZ)))
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.addCleanup(self.servidor.server_close)
        self.addCleanup(self.servidor.shutdown)
        for parche in (mock.patch.object(app, "salud", return_value={"ffmpeg": True, "llave": True}),
                       mock.patch.object(app, "queda_presupuesto", return_value=True),
                       mock.patch.object(app.time, "sleep")):
            parche.start()
            self.addCleanup(parche.stop)

    def pedir(self, metodo: str, ruta: str, cabeceras: dict | None = None, cuerpo: bytes = b"") -> tuple[int, dict]:
        c = http.client.HTTPConnection("127.0.0.1", self.servidor.server_port, timeout=5)
        h = {"Host": "retina.ejemplo.com", "X-Retina": "1", "Origin": SITIO, **(cabeceras or {})}
        c.request(metodo, ruta, cuerpo, h)
        r = c.getresponse()
        datos = r.read()
        c.close()
        try:
            return r.status, json.loads(datos or b"{}")
        except ValueError:
            return r.status, {}

    def datos(self, **cambios) -> dict:
        return {"X-Retina-Titulo": "Prueba", "X-Retina-Fecha": "2026-11-05 10:00", "X-Retina-Publicado": "0", **cambios}

    def test_el_panel_dice_que_hace_falta_el_codigo(self):
        self.assertEqual(self.pedir("GET", "/api/salud")[1].get("acceso"), True)

    def test_otro_host_no_entra(self):
        self.assertEqual(self.pedir("GET", "/api/salud", {"Host": "otro.com"})[0], 404)

    def test_sin_codigo_no_se_sube_nada(self):
        estado, cuerpo = self.pedir("POST", "/api/revisar", self.datos())
        self.assertEqual(estado, 401)
        self.assertIn("código", cuerpo["error"])
        self.fila.submit.assert_not_called()

    def test_sin_codigo_tampoco_se_arregla_nada(self):
        self.assertEqual(self.pedir("POST", "/api/apertura/a1b2c3d4e5f6")[0], 401)
        self.fila.submit.assert_not_called()

    def test_con_codigo_pasa_la_puerta(self):
        estado, _ = self.pedir("POST", "/api/apertura/a1b2c3d4e5f6", {"X-Retina-Acceso": CODIGO})
        self.assertEqual(estado, 202)
        self.fila.submit.assert_called_once()

    def test_un_video_de_mas_de_200_mb_se_rechaza_sin_leerlo(self):
        c = http.client.HTTPConnection("127.0.0.1", self.servidor.server_port, timeout=5)
        c.putrequest("POST", "/api/revisar", skip_host=True)
        for k, v in {"Host": "retina.ejemplo.com", "X-Retina": "1", "Origin": SITIO, "X-Retina-Acceso": CODIGO, **self.datos(),
                     "Content-Length": str(201 * 1024 * 1024)}.items():
            c.putheader(k, v)
        c.endheaders()
        r = c.getresponse()
        self.assertEqual(r.status, 400)
        self.assertIn("200", json.loads(r.read())["error"])
        c.close()

    def test_con_la_fila_llena_se_avisa(self):
        self.fila.pendientes.return_value = app.MAX_EN_FILA
        estado, cuerpo = self.pedir("POST", "/api/revisar", {**self.datos(), "X-Retina-Acceso": CODIGO})
        self.assertEqual(estado, 503)
        self.assertTrue(cuerpo["error"])

    def test_sin_presupuesto_se_avisa_antes_de_recibir_el_video(self):
        with mock.patch.object(app, "queda_presupuesto", return_value=False):
            estado, cuerpo = self.pedir("POST", "/api/revisar", {**self.datos(), "X-Retina-Acceso": CODIGO})
        self.assertEqual(estado, 503)
        self.assertIn("presupuesto", cuerpo["error"])


if __name__ == "__main__":
    unittest.main()
