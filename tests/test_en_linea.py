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
from concurrent.futures import ThreadPoolExecutor
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

    def test_una_carpeta_que_desaparece_a_media_limpieza_no_truena(self):
        with tempfile.TemporaryDirectory() as d:
            casos = Path(d)
            (casos / "a1b2c3d4e5f6").mkdir()
            with mock.patch.object(Path, "stat", side_effect=FileNotFoundError):
                app.limpiar(casos)

    def test_la_limpieza_periodica_no_depende_de_que_alguien_suba_algo(self):
        vueltas = []

        class Alto(Exception):
            pass

        def dormir(_):
            if len(vueltas) >= 2:
                raise Alto
        with tempfile.TemporaryDirectory() as d, mock.patch.object(app, "limpiar", side_effect=lambda c: vueltas.append(c)), \
                mock.patch.object(app.time, "sleep", dormir), self.assertRaises(Alto):
            app.limpiar_siempre(Path(d))
        self.assertEqual(len(vueltas), 2)

    def test_una_falla_de_limpieza_no_mata_las_siguientes(self):
        intentos = []

        class Alto(Exception):
            pass

        def limpiar(_):
            intentos.append(1)
            raise OSError("disco")

        def dormir(_):
            if len(intentos) >= 2:
                raise Alto
        with tempfile.TemporaryDirectory() as d, mock.patch.object(app, "limpiar", limpiar), \
                mock.patch.object(app.time, "sleep", dormir), self.assertRaises(Alto):
            app.limpiar_siempre(Path(d))
        self.assertEqual(len(intentos), 2)


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


    def test_apartar_lugar_es_atomico_y_tiene_tope(self):
        fila = app.FilaContada()
        with ThreadPoolExecutor(20) as hilos:
            logrados = sum(hilos.map(lambda _: fila.apartar(app.MAX_EN_FILA), range(50)))
        self.assertEqual((logrados, fila.pendientes()), (app.MAX_EN_FILA, app.MAX_EN_FILA))
        fila.soltar()
        self.assertEqual(fila.pendientes(), app.MAX_EN_FILA - 1)


class CostoDeCadaVideo(unittest.TestCase):
    """El límite vale aunque el archivo mienta sobre su duración o traiga un formato que hay que convertir."""

    def test_un_titulo_del_archivo_no_engana_a_la_duracion(self):
        info = ("  Metadata:\n    title           : Duration: 00:00:01.00, start: 0\n"
                "  Duration: 02:00:00.00, start: 0.000000, bitrate: 1 kb/s\n")
        self.assertEqual(segmentar.duracion_s(Path("v.mp4"), info), 7200.0)

    def test_un_archivo_que_hay_que_convertir_se_mide_antes_de_gastar_en_el(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"RETINA_DURACION_MAXIMA_S": "300"}), \
                mock.patch.object(app, "duracion_s", return_value=4000.0), mock.patch.object(app, "convertir_a_mp4") as convertir:
            c = Path(d)
            (c / app.SUBIDA).write_bytes(b"x")
            app.revisar(c, {"idioma": "es"}, {})
            estado = json.loads((c / "estado.json").read_text(encoding="utf-8"))
        convertir.assert_not_called()
        self.assertEqual(estado["estado"], "error")
        self.assertIn("5 minutos", estado["mensaje"])

    def test_la_conversion_tiene_tope_de_duracion_y_de_tamano(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"RETINA_DURACION_MAXIMA_S": "300"}), \
                mock.patch("retina.segmentar._ffmpeg", return_value="ffmpeg"), mock.patch.object(app.subprocess, "run") as correr, \
                mock.patch.object(app.os, "replace"):
            correr.return_value = mock.Mock(returncode=0)
            c = Path(d)
            (c / "convirtiendo.mp4").write_bytes(b"x")
            app.convertir_a_mp4(c / "a.webm", c / "video.mp4")
        args = correr.call_args.args[0]
        self.assertEqual(args[args.index("-t") + 1], "300")
        self.assertIn("-fs", args)

    def test_cada_salida_de_segmentar_se_corta_en_el_maximo(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"RETINA_DURACION_MAXIMA_S": "300"}), \
                mock.patch.object(segmentar, "_info", return_value=""), mock.patch.object(segmentar, "duracion_s", return_value=60.0), \
                mock.patch.object(segmentar, "pistas", return_value=(True, True)), mock.patch.object(segmentar, "_correr") as correr:
            try:
                segmentar.segmentar(Path(d) / "v.mp4", Path(d))
            except (FileNotFoundError, IndexError, ValueError):
                pass  # sin ffmpeg de verdad no hay cuadros: aquí solo importan sus argumentos
        self.assertGreaterEqual(correr.call_count, 2)
        for llamada in correr.call_args_list:
            args = llamada.args[0]
            self.assertEqual(args[args.index("-t") + 1], "300", args)


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
        self.addCleanup(app._APERTURAS.clear)
        self.fila = mock.Mock()
        self.fila.apartar.return_value = True
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

    def test_cada_pedido_suelta_el_lugar_que_aparto_aunque_falle(self):
        self.assertEqual(self.pedir("POST", "/api/revisar", {**self.datos(), "X-Retina-Fecha": "ayer", "X-Retina-Acceso": CODIGO})[0], 400)
        self.assertEqual(self.pedir("POST", "/api/apertura/a1b2c3d4e5f6", {"X-Retina-Acceso": CODIGO})[0], 202)
        self.assertEqual(self.fila.apartar.call_count, self.fila.soltar.call_count)
        self.assertEqual(self.fila.soltar.call_count, 2)

    def test_con_la_fila_llena_se_avisa(self):
        self.fila.apartar.return_value = False
        estado, cuerpo = self.pedir("POST", "/api/revisar", {**self.datos(), "X-Retina-Acceso": CODIGO})
        self.assertEqual(estado, 503)
        self.assertTrue(cuerpo["error"])

    def test_sin_presupuesto_se_avisa_antes_de_recibir_el_video(self):
        with mock.patch.object(app, "queda_presupuesto", return_value=False):
            estado, cuerpo = self.pedir("POST", "/api/revisar", {**self.datos(), "X-Retina-Acceso": CODIGO})
        self.assertEqual(estado, 503)
        self.assertIn("presupuesto", cuerpo["error"])
        self.assertEqual(self.fila.apartar.call_count, self.fila.soltar.call_count)


if __name__ == "__main__":
    unittest.main()
