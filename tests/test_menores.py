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
import os
import re
import tempfile
from unittest import mock

from retina import app, demo, meta_api, retina, transcribir  # noqa: E402


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


class ProxyEnLinea(unittest.TestCase):
    """B12: el panel consulta cada 1.2 s (50 por minuto) y el límite era de 30; y proxy_params solo existe en Debian y Ubuntu."""

    def setUp(self):
        self.conf = (RAIZ / "deploy" / "proxy-en-linea.conf").read_text(encoding="utf-8")

    def test_el_limite_solo_cuenta_los_POST(self):
        zona = re.search(r"limit_req_zone\s+(\S+)\s+zone=retina_api", self.conf).group(1)
        self.assertNotEqual(zona, "$binary_remote_addr")  # con la IP a secas, el sondeo del panel también cuenta
        self.assertRegex(self.conf, r"map \$request_method " + re.escape(zona) + r" \{[^}]*POST\s+\$binary_remote_addr;[^}]*default\s+\"\";")

    def test_no_depende_de_proxy_params(self):
        self.assertNotIn("proxy_params", self.conf)
        for cabecera in ("Host $host", "X-Forwarded-For $proxy_add_x_forwarded_for", "X-Forwarded-Proto $scheme"):
            self.assertIn("proxy_set_header " + cabecera, self.conf)


class ReinicioAMediaRevision(unittest.TestCase):
    """B13: si Retina se cierra a media revisión, estado.json se queda en «procesando» y el panel espera sin fin."""

    def _caso(self, d, nombre, estado=None, archivos=()):
        c = Path(d) / nombre
        c.mkdir()
        if estado is not None:
            (c / "estado.json").write_text(json.dumps(estado), encoding="utf-8")
        for a in archivos:
            (c / a).write_text("x", encoding="utf-8")
        return c

    def _estado(self, carpeta):
        return app.estado(carpeta)

    def test_lo_que_estaba_procesando_queda_como_interrumpido_en_su_idioma(self):
        with tempfile.TemporaryDirectory() as d:
            es = self._caso(d, "a" * 12, {"estado": "procesando", "idioma": "es"})
            en = self._caso(d, "b" * 12, {"estado": "procesando", "idioma": "en"})
            self.assertEqual(app.marcar_interrumpidas(Path(d)), 2)
            self.assertEqual(self._estado(es), {"estado": "error", "mensaje": app.texto("es", "interrumpida")})
            self.assertEqual(self._estado(en), {"estado": "error", "mensaje": app.texto("en", "interrumpida")})
            self.assertNotEqual(app.texto("es", "interrumpida"), app.texto("en", "interrumpida"))

    def test_lo_que_esperaba_turno_en_la_fila_tambien(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._caso(d, "c" * 12, None, ("video.mp4",))
            self.assertEqual(app.marcar_interrumpidas(Path(d)), 1)
            self.assertEqual(self._estado(c)["estado"], "error")

    def test_no_toca_lo_terminado_ni_carpetas_ajenas(self):
        with tempfile.TemporaryDirectory() as d:
            listo = self._caso(d, "d" * 12, {"estado": "listo"})
            con_error = self._caso(d, "e" * 12, {"estado": "error", "mensaje": "otra cosa"})
            cli = self._caso(d, "corrida-por-linea", {"estado": "procesando"})  # no la creó el panel: no es de este programa
            hecha = self._caso(d, "f" * 12, None, ("video.mp4", "resultado.json"))  # corrida de línea de comandos ya terminada
            self.assertEqual(app.marcar_interrumpidas(Path(d)), 0)
            self.assertEqual(self._estado(listo), {"estado": "listo"})
            self.assertEqual(self._estado(con_error)["mensaje"], "otra cosa")
            self.assertEqual(json.loads((cli / "estado.json").read_text(encoding="utf-8")), {"estado": "procesando"})
            self.assertFalse((hecha / "estado.json").exists())

    def test_la_revision_guarda_su_idioma_sin_mostrarlo_en_el_estado(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(retina, "correr", side_effect=lambda *a, **k: self._ver(d)):
            datos = {"codigo": "A", "talento": "", "fecha": "2026-01-01 10:00", "titulo": "t", "publicado": True, "idioma": "en"}
            self.vista = None
            app.revisar(Path(d), datos, {"modelo": None, "arranque": None, "voz": None})
            self.assertEqual(self.vista, {"estado": "procesando", "idioma": "en"})

    def _ver(self, d):
        self.vista = json.loads((Path(d) / "estado.json").read_text(encoding="utf-8"))
        return {}


class IdiomaDeLaVoz(unittest.TestCase):
    """B14: un título sin palabras comunes («Sourdough Bread Recipe») no dice el idioma; no se puede suponer español."""

    def _idiomas_pedidos(self, lengua, idioma_panel=None):
        import wave
        with tempfile.TemporaryDirectory() as d:
            c = Path(d)
            with wave.open(str(c / "audio.wav"), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(bytes(4800))
            (c / "manifiesto.json").write_text(json.dumps({"audio": "audio.wav", "duracion_s": 0.1}), encoding="utf-8")
            with mock.patch.object(meta_api, "transcribir_wav", return_value={"turns": []}) as api:
                if idioma_panel is None:
                    transcribir.transcribir(c, lengua)
                else:
                    transcribir.transcribir(c, lengua, idioma_panel)
            return api.call_args.kwargs["idiomas"]

    def test_el_titulo_en_ingles_pide_ingles_y_el_claro_en_espanol_pide_espanol(self):
        self.assertEqual(self._idiomas_pedidos("en"), ("English",))
        self.assertEqual(self._idiomas_pedidos("es"), ("Spanish",))

    def test_sin_pista_se_le_dejan_los_dos_idiomas_con_el_del_panel_primero(self):
        self.assertEqual(self._idiomas_pedidos(None, "en"), ("English", "Spanish"))
        self.assertEqual(self._idiomas_pedidos(None, "es"), ("Spanish", "English"))
        self.assertEqual(self._idiomas_pedidos(None), ("Spanish", "English"))

    def test_el_orquestador_le_pasa_el_idioma_del_panel(self):
        self.assertIsNone(transcribir.idioma_de("Sourdough Bread Recipe"))
        fuente = (RAIZ / "src" / "retina" / "retina.py").read_text(encoding="utf-8")
        self.assertIn("transcribir.idioma_de(titulo), idioma)", fuente)


class CarpetaDeOtroVideo(unittest.TestCase):
    """B15: si la carpeta se reusa con otro video, los cuadros del video anterior no se pueden quedar."""

    def test_cambiar_de_video_borra_los_cuadros_y_lo_pagado(self):
        with tempfile.TemporaryDirectory() as d:
            salida, video = Path(d) / "caso", Path(d) / "v.mp4"
            video.write_bytes(b"uno")
            retina.preparar_carpeta(video, salida)
            (salida / "cuadros").mkdir()
            (salida / "cuadros" / "c00099.jpg").write_bytes(b"x")
            (salida / "describir.json").write_text("{}", encoding="utf-8")
            retina.preparar_carpeta(video, salida)  # el mismo video: se conserva todo
            self.assertTrue((salida / "cuadros" / "c00099.jpg").exists() and (salida / "describir.json").exists())
            video.write_bytes(b"otro")
            retina.preparar_carpeta(video, salida)
            self.assertFalse((salida / "cuadros").exists() or (salida / "describir.json").exists())


class RegistroDeCostosTruncado(unittest.TestCase):
    """B16: una línea cortada a medias en costos.jsonl (corrida o disco caídos) tumbaba cada llamada a la API."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.costos = Path(self.tmp.name) / "costos.jsonl"
        env = mock.patch.dict(os.environ, {"RETINA_COSTOS": str(self.costos), "RETINA_ENV": str(Path(self.tmp.name) / "no-hay.env")})
        env.start()
        self.addCleanup(env.stop)

    def test_una_linea_cortada_no_tumba_el_conteo(self):
        self.costos.write_text('{"servicio": "a", "usd": 1.5}\n{"servicio": "b", "us', encoding="utf-8")
        self.assertEqual(meta_api.gastado_usd(), 1.5)
        meta_api._revisar_tope(0.1)  # antes de arreglarlo, esto lanzaba JSONDecodeError

    def test_lo_que_se_anota_despues_no_se_pega_a_la_linea_cortada(self):
        self.costos.write_text('{"servicio": "a", "usd": 1.5}\n{"servicio": "b", "us', encoding="utf-8")
        meta_api._registrar("c", "m", 1.0, 2.0)
        self.assertEqual(meta_api.gastado_usd(), 3.5)

    def test_una_linea_que_no_es_un_objeto_tampoco_estorba(self):
        self.costos.write_text('[1, 2]\n"suelta"\n{"servicio": "a", "usd": 2}\n', encoding="utf-8")
        self.assertEqual(meta_api.gastado_usd(), 2.0)


if __name__ == "__main__":
    unittest.main()
