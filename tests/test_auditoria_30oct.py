"""Correcciones de la auditoría del 30-oct (noche): cola, limpieza de subidas, traducción, normas en otros alfabetos,
idioma, avance y el panel. Sin API, sin llaves y sin red. Corren con:  python -m unittest discover -s tests
"""
from __future__ import annotations

import functools
import http.client
import http.server
import json
import os
import re
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from retina import app, demo, explicar, meta_api, normas, retina, segmentar, transcribir, traducir  # noqa: E402

DATOS_APP = {"titulo": "x", "talento": "", "codigo": "", "fecha": "2026-11-05 10:00", "publicado": False, "idioma": "es"}


def CIFRAS(texto: str) -> str:
    return "Texto " + "".join(re.findall(r"\d+", texto))


def caja(tipo: bytes, tamano: int = 24) -> bytes:
    return tamano.to_bytes(4, "big") + tipo + bytes(4)


class Servidores(unittest.TestCase):
    def test_x2_la_cola_de_conexiones_aguanta_una_rafaga(self):
        self.assertGreaterEqual(demo.ServidorExclusivo.request_queue_size, 128)
        self.assertGreaterEqual(app.ServidorExclusivo.request_queue_size, 128)

    def test_x1_sin_caso_explicito_el_panel_elige_el_caso_por_idioma(self):
        self.assertEqual(demo.destino(None), "/panel/")
        self.assertEqual(demo.destino("casos/demo/resultado.json"), "/panel/?caso=/casos/demo/resultado.json")

    def test_x1_un_caso_fuera_del_repo_no_se_acepta(self):
        with self.assertRaises(SystemExit):
            demo.destino("../fuera/resultado.json")

    def test_x1_se_sirven_los_dos_casos_de_la_demo(self):
        for caso in ("demo", "demo-en"):
            with self.subTest(caso=caso):
                ruta = demo.ruta_local(f"/casos/{caso}/resultado.json", RAIZ, None)
                self.assertTrue(ruta and ruta.is_file(), caso)

    def test_x1_nginx_abre_el_panel_sin_caso(self):
        conf = (RAIZ / "deploy" / "nginx.conf").read_text(encoding="utf-8")
        self.assertRegex(conf, r"location = / \{ return 302 /panel/;")


class FormatosDeVideo(unittest.TestCase):
    def test_s2_una_cabecera_suelta_ya_no_es_un_video(self):
        for malo in (caja(b"free", 2), caja(b"skip", 3), b"\x00\x00\x00\x00" + b"ftyp" + bytes(4),
                     caja(b"ftyp", 2), caja(b"ftyp", 1 << 20), b"FLV\x09\x05\x00\x00\x00\x09\x00\x00\x00",
                     b"FLV\x01\x05\xff\xff\xff\xff\x00\x00\x00"):
            with self.subTest(cabeza=malo):
                self.assertIsNone(app.tipo_de_video(malo))

    def test_s2_las_firmas_de_verdad_siguen_entrando(self):
        self.assertEqual(app.tipo_de_video(caja(b"ftyp")), "mp4")
        self.assertEqual(app.tipo_de_video(caja(b"wide", 8)), "convertir")
        self.assertEqual(app.tipo_de_video(caja(b"moov", 1 << 20)), "convertir")
        self.assertEqual(app.tipo_de_video(b"\x1aE\xdf\xa3" + bytes(8)), "convertir")
        self.assertEqual(app.tipo_de_video(b"RIFF" + bytes(4) + b"AVI "), "convertir")
        self.assertEqual(app.tipo_de_video(b"FLV\x01\x05\x00\x00\x00\x09\x00\x00\x00"), "convertir")

    def test_s2_ffmpeg_solo_abre_los_contenedores_que_se_aceptan(self):
        i = segmentar.PROTOCOLOS.index("-format_whitelist")
        lista = segmentar.PROTOCOLOS[i + 1].split(",")
        for ok in ("matroska", "webm", "avi", "flv", "mov", "mp4"):
            self.assertIn(ok, lista)
        for malo in ("concat", "hls", "image2", "lavfi", "rtsp"):
            self.assertNotIn(malo, lista)


class SubidasQueFallan(unittest.TestCase):
    def carpeta(self, d: str, nombre: str = "a1b2c3d4e5f6") -> Path:
        c = Path(d) / nombre
        c.mkdir()
        for n in ("video.mp4", app.SUBIDA, "convirtiendo.mp4", "ligero.mp4", "audio.wav"):
            (c / n).write_bytes(b"x")
        (c / "cuadros").mkdir()
        (c / "cuadros" / "c00001.jpg").write_bytes(b"x")
        return c

    def revisar_con(self, falla: BaseException) -> Path:
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        c = self.carpeta(d.name)
        with mock.patch.object(retina, "correr", side_effect=falla):
            app.revisar(c, DATOS_APP, {"modelo": None, "arranque": None, "voz": None})
        return c

    def test_s1_el_video_se_borra_en_toda_salida_de_error(self):
        for falla in (RuntimeError("x"), meta_api.TopeAlcanzado("t"), segmentar.Aviso("no_lee", "x"), ValueError("v")):
            with self.subTest(falla=type(falla).__name__):
                c = self.revisar_con(falla)
                self.assertEqual(json.loads((c / "estado.json").read_text(encoding="utf-8"))["estado"], "error")
                for n in ("video.mp4", app.SUBIDA, "convirtiendo.mp4", "ligero.mp4", "audio.wav"):
                    self.assertFalse((c / n).exists(), n)
                self.assertFalse((c / "cuadros").exists())

    def test_s1_si_la_revision_sale_bien_el_video_se_queda(self):
        with tempfile.TemporaryDirectory() as d:
            c = self.carpeta(d)
            (c / app.SUBIDA).unlink()
            with mock.patch.object(retina, "correr", return_value={}):
                app.revisar(c, DATOS_APP, {"modelo": None, "arranque": None, "voz": None})
            self.assertTrue((c / "video.mp4").exists())

    def test_s1_al_arrancar_se_limpia_lo_que_dejo_una_corrida_cerrada(self):
        with tempfile.TemporaryDirectory() as d:
            interrumpida, fallida, bien, fantasma = (self.carpeta(d, n) for n in ("a" * 12, "b" * 12, "c" * 12, "d" * 12))
            (interrumpida / "estado.json").write_text('{"estado": "procesando"}', encoding="utf-8")
            (fallida / "estado.json").write_text('{"estado": "error"}', encoding="utf-8")
            (bien / "estado.json").write_text('{"estado": "listo"}', encoding="utf-8")
            (bien / "resultado.json").write_text("{}", encoding="utf-8")
            for n in ("video.mp4", app.SUBIDA, "convirtiendo.mp4", "ligero.mp4", "audio.wav"):
                (fantasma / n).unlink()  # carpeta fantasma: una subida cortada, sin estado ni video
            app.marcar_interrumpidas(Path(d))
            app.limpiar_al_arrancar(Path(d))
            self.assertFalse((interrumpida / "video.mp4").exists())
            self.assertFalse((fallida / "video.mp4").exists())
            self.assertTrue((bien / "video.mp4").exists())
            self.assertFalse(fantasma.exists())

    def test_s1_la_cuota_rechaza_lo_que_no_cabe(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a1b2c3d4e5f6").mkdir()
            (Path(d) / "a1b2c3d4e5f6" / "v.mp4").write_bytes(b"x" * 1000)
            self.assertEqual(app.ocupado_bytes(Path(d)), 1000)
            with mock.patch.object(app, "CUOTA_MB", 1), mock.patch.object(app, "CUOTA_EN_LINEA_MB", 1):
                self.assertTrue(app.cabe(Path(d), 1000, False))
                self.assertFalse(app.cabe(Path(d), 2 * 1024 * 1024, False))
                self.assertFalse(app.cabe(Path(d), 2 * 1024 * 1024, True))


class SubidaPorHttp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.casos = Path(self.tmp.name)
        self.fila = mock.Mock()
        clase = type("Manejador", (app.ConSubida,), {
            "casos": self.casos, "fila": self.fila, "talentos": [], "modelos": {"modelo": None, "arranque": None, "voz": None},
            "hosts": ("127.0.0.1", "localhost"), "en_linea": None})
        self.servidor = demo.ServidorExclusivo(("127.0.0.1", 0), functools.partial(clase, directory=str(RAIZ)))
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.addCleanup(self.servidor.server_close)
        self.addCleanup(self.servidor.shutdown)
        p = mock.patch.object(app, "salud", return_value={"ffmpeg": True, "llave": True})
        p.start()
        self.addCleanup(p.stop)
        self.cab = {"Host": "127.0.0.1", "X-Retina": "1", "X-Retina-Titulo": "Pan", "X-Retina-Fecha": "2026-11-05 10:00",
                    "X-Retina-Publicado": "0"}

    def cruda(self, cabeceras: dict, cuerpo: bytes = b"", cerrar_escritura: bool = False) -> bytes:
        s = socket.create_connection(("127.0.0.1", self.servidor.server_port), timeout=10)
        enc = "".join(f"{k}: {v}\r\n" for k, v in cabeceras.items())
        s.sendall(f"POST /api/revisar HTTP/1.1\r\n{enc}\r\n".encode("utf-8") + cuerpo)
        if cerrar_escritura:
            s.shutdown(socket.SHUT_WR)
        r = b""
        while t := s.recv(4096):
            r += t
        s.close()
        return r

    def test_b12_un_content_length_con_superindice_no_truena(self):
        r = self.cruda({**self.cab, "Content-Length": "²"}, cerrar_escritura=True)
        self.assertIn(b" 400 ", r.split(b"\r\n", 1)[0])

    def test_b12_un_content_length_enorme_tampoco(self):
        self.assertIsNone(app.largo_valido("9" * 5000))
        self.assertIsNone(app.largo_valido("²"))
        self.assertIsNone(app.largo_valido("-5"))
        self.assertEqual(app.largo_valido("42"), 42)

    def test_b12_una_subida_que_se_corta_con_error_no_deja_carpeta(self):
        cuerpo = caja(b"ftyp") + b"x" * 1000
        s = socket.create_connection(("127.0.0.1", self.servidor.server_port), timeout=10)
        enc = "".join(f"{k}: {v}\r\n" for k, v in {**self.cab, "Content-Length": "5000000"}.items())
        s.sendall(f"POST /api/revisar HTTP/1.1\r\n{enc}\r\n".encode() + cuerpo)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00")
        s.close()  # reinicio brusco de la conexión: rfile.read lanza ConnectionResetError
        for _ in range(100):
            if not list(self.casos.iterdir()):
                break
            threading.Event().wait(0.05)
        self.assertEqual(list(self.casos.iterdir()), [])
        self.fila.submit.assert_not_called()

    def test_b4_un_rechazo_sin_leer_el_cuerpo_no_aborta_la_respuesta(self):
        """El cliente manda parte del cuerpo y el servidor contesta antes de leerlo: la respuesta tiene que llegar."""
        cuerpo = b"<html>" + b"x" * 200_000
        for i in range(5):
            r = self.cruda({**self.cab, "Content-Length": str(len(cuerpo))}, cuerpo)
            self.assertIn(b" 400 ", r.split(b"\r\n", 1)[0], i)

    def test_s1_sin_espacio_se_avisa_antes_de_recibir_el_video(self):
        cuerpo = caja(b"ftyp") + b"x" * 1000
        with mock.patch.object(app, "cabe", return_value=False):
            r = self.cruda({**self.cab, "Content-Length": str(len(cuerpo))}, cuerpo)
        self.assertIn(b" 503 ", r.split(b"\r\n", 1)[0])
        self.assertEqual(list(self.casos.iterdir()), [])


class Traduccion(unittest.TestCase):
    CASO = {"idioma": "en", "video": {"titulo": "t"}, "explicacion": {"por_que": "The voice repeats.", "lo_que_funciona": "Good hook.",
            "que_cambiar": "", "lo_bueno": ["A"], "lo_flojo": [], "pasos": [], "mejoras_opcionales": [],
            "storyboard": ["Show the pan at second 0."], "no_pude_verificar": ["Nothing."]}}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name) / "a1b2c3d4e5f6"
        self.d.mkdir()
        self.guardar(self.CASO)
        self.addCleanup(app._TRADUCCIONES.clear)

    def guardar(self, r: dict) -> None:
        (self.d / "resultado.json").write_text(json.dumps(r), encoding="utf-8")

    def test_s4_dos_traducciones_a_la_vez_se_pagan_una_sola_vez(self):
        llamadas = []

        def pedir(textos, idioma, insistir=False):
            llamadas.append(1)
            time.sleep(0.3)
            return [CIFRAS(t) for t in textos]
        resultados = []
        with mock.patch.object(app, "salud", return_value={"ffmpeg": True, "llave": True}), mock.patch.object(traducir, "pedir", pedir):
            hilos = [threading.Thread(target=lambda: resultados.append(app.pedir_traduccion(self.d, "es"))) for _ in range(4)]
            for h in hilos:
                h.start()
            for h in hilos:
                h.join()
        self.assertEqual(len(llamadas), 1)
        self.assertEqual([c for c, _ in resultados], [200] * 4)

    def test_s3_tras_varios_fallos_seguidos_ya_no_se_intenta(self):
        with mock.patch.object(app, "salud", return_value={"ffmpeg": True, "llave": True}), \
                mock.patch.object(traducir, "pedir", side_effect=RuntimeError("x")) as pedir:
            codigos = [app.pedir_traduccion(self.d, "es")[0] for _ in range(app.MAX_INTENTOS_TRADUCCION + 2)]
        self.assertEqual(pedir.call_count, app.MAX_INTENTOS_TRADUCCION)
        self.assertEqual(codigos[-1], 429)

    def test_s3_nginx_limita_la_traduccion(self):
        conf = (RAIZ / "deploy" / "proxy-en-linea.conf").read_text(encoding="utf-8")
        self.assertRegex(conf, r"location /api/traducir/ \{[^}]*limit_req zone=retina_api")

    def test_b3_no_se_traduce_una_revision_que_sigue_en_curso(self):
        (self.d / "estado.json").write_text('{"estado": "procesando"}', encoding="utf-8")
        with mock.patch.object(app, "salud", return_value={"ffmpeg": True, "llave": True}), \
                mock.patch.object(traducir, "pedir", side_effect=AssertionError("gastó")):
            codigo, cuerpo = app.pedir_traduccion(self.d, "es")
        self.assertEqual(codigo, 409)
        self.assertTrue(cuerpo["error"])
        self.assertFalse((self.d / "resultado-es.json").exists())

    def test_b3_una_traduccion_de_un_resultado_que_cambio_se_rehace(self):
        with mock.patch.object(traducir, "pedir", side_effect=lambda t, i, insistir=False: [CIFRAS(x) for x in t]):
            traducir.traducir(self.d, "es")
        self.guardar({**self.CASO, "explicacion": {**self.CASO["explicacion"], "por_que": "It changed."}})
        with mock.patch.object(traducir, "pedir", side_effect=lambda t, i, insistir=False: [CIFRAS(x) for x in t]) as pedir:
            traducir.traducir(self.d, "es")
        pedir.assert_called_once()

    def test_q7_el_storyboard_se_traduce_y_lo_que_no_se_muestra_no_se_paga(self):
        textos = [c[k] for c, k in traducir.lugares(self.CASO)]
        self.assertIn("Show the pan at second 0.", textos)
        self.assertNotIn("Nothing.", textos)

    def test_s5_una_traduccion_no_cambia_que_regla_rompe(self):
        # El original rompe una regla (presentación) y la traducción rompe otra (pide comentar): el conteo no las distingue.
        original = "Cut the greeting"
        self.assertTrue(traducir.aceptable(original, original))
        self.assertFalse(traducir.aceptable("Corta el saludo", "Comenta abajo y sigue la cuenta"))

    def test_s5_una_traduccion_no_trae_enlaces_nuevos(self):
        for malo in ("Corta 2 segundos y mira https://malo.example/x", "Corta 2 segundos en www.malo.example",
                     "Corta 2 segundos, escribe a ayuda@malo.example", "Corta 2 segundos: malo.example/oferta"):
            with self.subTest(malo=malo):
                self.assertFalse(traducir.aceptable("Cut 2 seconds.", malo))
        self.assertTrue(traducir.aceptable("Visit site.example for 2 tips", "Visita site.example para 2 consejos"))


class Explicar(unittest.TestCase):
    def test_s6_los_enlaces_se_bloquean_en_lo_que_ve_la_persona(self):
        for campo in ("por_que", "lo_que_funciona", "que_cambiar"):
            self.assertTrue(explicar.enlaces(f"mira https://malo.example/x ahora"), campo)
        self.assertTrue(explicar.enlaces("entra a www.malo.example"))
        self.assertTrue(explicar.enlaces("escribe a ayuda@malo.example"))
        self.assertTrue(explicar.enlaces("compra en malo.com/oferta"))
        self.assertFalse(explicar.enlaces("Entre el segundo 4.5 y el 9.2 la voz se detiene."))
        self.assertFalse(explicar.enlaces("Pon el dato en pantalla. Luego corta."))

    def test_q2_un_json_truncado_se_reintenta_y_no_tumba_la_tarjeta(self):
        buena = {"por_que": "", "lo_que_funciona": "", "lo_bueno": ["a"], "lo_flojo": [], "que_cambiar": "", "pasos": [],
                 "mejoras_opcionales": [], "tipo_de_cambio": "ninguno", "momento_s": 1.0, "anzuelo_detectado": "ninguno",
                 "anzuelo_frase": "", "anzuelo_momento_s": -1, "confianza": "baja", "storyboard": [], "no_pude_verificar": []}
        respuestas = [json.JSONDecodeError("truncado", "{", 1), buena]

        def pedir(datos, aviso, motor):
            r = respuestas.pop(0)
            if isinstance(r, Exception):
                raise r
            return dict(r)
        datos = {"duracion_video_s": 60.0, "primer_cuarto_s": [3.0, 15.0], "nivel_de_riesgo": "bajo"}
        salida, intentos, _ = explicar.escribir(datos, ("api",), pedir)
        self.assertEqual(len(intentos), 2)
        self.assertIsNotNone(salida)

    def test_q2_si_siempre_falla_el_error_sigue_subiendo(self):
        def pedir(datos, aviso, motor):
            raise json.JSONDecodeError("truncado", "{", 1)
        with self.assertRaises(ValueError):
            explicar.escribir({"duracion_video_s": 60.0, "primer_cuarto_s": [3.0, 15.0], "nivel_de_riesgo": "bajo"}, ("api",), pedir)


class NormasOtrosAlfabetos(unittest.TestCase):
    def datos(self, dice: str) -> dict:
        return {"titulo": "t", "duracion_video_s": 60.0, "se_ve": [], "se_dice": [{"segundo": 12, "dice": dice}]}

    def hallazgo(self, evidencia: str, segundo: int = 12) -> dict:
        return {"norma": "bienes_restringidos", "segundo": segundo, "evidencia": evidencia, "por_que": "Podría ser venta restringida."}

    def test_q1_la_evidencia_en_arabe_chino_o_hindi_se_sostiene(self):
        casos = {"ar": "اشتري هذا المنتج الآن واتصل بنا اليوم", "zh": "现在购买这个产品并给我们打电话", "hi": "अभी यह उत्पाद खरीदें और हमें कॉल करें"}
        for nombre, frase in casos.items():
            with self.subTest(idioma=nombre):
                datos = self.datos(f"hola {frase} gracias")
                self.assertEqual(len(normas.filtrar([self.hallazgo(frase)], datos)), 1)

    def test_q1_una_cita_inventada_en_otro_alfabeto_se_descarta(self):
        self.assertEqual(normas.filtrar([self.hallazgo("现在购买这个产品并给我们打电话")], self.datos("今天天气很好我们去公园玩")), [])

    def test_q1_lo_que_no_se_pudo_verificar_por_alfabeto_se_dice(self):
        video = self.datos("اشتري هذا المنتج الآن واتصل بنا اليوم")
        # el modelo cita en español algo que dice un video en árabe: no hay cómo comprobarlo, y no es «sin riesgos»
        revisados = normas.verificar([self.hallazgo("compra este producto ahora y llámanos hoy")], video)
        self.assertEqual(revisados["hallazgos"], [])
        self.assertTrue(revisados["no_verificado"])

    def test_q1_un_video_en_espanol_sin_dudas_no_trae_la_marca(self):
        video = self.datos("Escribe a este número y te lo mando hoy mismo")
        r = normas.verificar([self.hallazgo("te lo mando hoy mismo")], video)
        self.assertEqual((len(r["hallazgos"]), r["no_verificado"]), (1, False))
        self.assertFalse(normas.verificar([], video)["no_verificado"])

    def test_q1_el_resultado_guardado_trae_la_marca(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            (d / "manifiesto.json").write_text(json.dumps({"duracion_s": 60.0, "tramos": [{"inicio_s": i * 1.5, "fin_s": (i + 1) * 1.5} for i in range(40)]}), encoding="utf-8")
            (d / "describir.json").write_text(json.dumps({"tramos": []}), encoding="utf-8")
            (d / "transcribir.json").write_text(json.dumps({"turnos": [{"startMs": 12000, "transcript": "اشتري هذا المنتج الآن واتصل بنا اليوم"}]}), encoding="utf-8")
            texto = json.dumps({"hallazgos": [self.hallazgo("compra este producto ahora y llámanos hoy")]})
            r = {"output": [{"type": "message", "content": [{"type": "output_text", "text": texto}]}]}
            with mock.patch.object(meta_api, "responder", return_value=r):
                s = normas.revisar(d, "es", "t")
        self.assertEqual((s["hallazgos"], s["no_verificado"]), ([], True))


class Idioma(unittest.TestCase):
    def test_b10_portugues_y_frances_no_pasan_por_espanol(self):
        pt = "Eu não sei o que você quer, mas isso é muito bom para todos nós e também para os amigos"
        fr = "Je ne sais pas ce que vous voulez, mais c'est très bien pour tous les amis et pour nous"
        self.assertEqual(transcribir.idioma_detectado(pt), "pt")
        self.assertIsNone(transcribir.idioma_de(pt))  # apertura y tarjeta solo hablan es o en
        self.assertEqual(transcribir.idioma_detectado(fr), "fr")

    def test_b10_lo_que_ya_funcionaba_sigue_igual(self):
        self.assertEqual(transcribir.idioma_de("Así se tejen las bufandas de lana que nadie te enseñó"), "es")
        self.assertEqual(transcribir.idioma_de("How to fix the opening of your video in three steps"), "en")
        self.assertIsNone(transcribir.idioma_de("Tutorial"))

    def test_b10_otro_idioma_avisa_con_cualquier_idioma_que_no_sea_espanol(self):
        self.assertTrue(retina.es_otro_idioma("pt"))
        self.assertTrue(retina.es_otro_idioma("fr"))
        self.assertTrue(retina.es_otro_idioma("en"))
        self.assertFalse(retina.es_otro_idioma("es"))
        self.assertFalse(retina.es_otro_idioma(None))


class AvanceYEstado(unittest.TestCase):
    def test_b1_un_permission_error_al_anotar_el_avance_se_reintenta(self):
        with tempfile.TemporaryDirectory() as d:
            real, intentos = os.replace, []

            def replace(a, b):
                intentos.append(1)
                if len(intentos) < 3:
                    raise PermissionError("el panel lo tiene abierto")
                real(a, b)
            with mock.patch.object(retina.os, "replace", replace), mock.patch.object(retina.time, "sleep"):
                retina.anotar_avance(Path(d), "mirando", {})
            self.assertEqual(json.loads((Path(d) / "avance.json").read_text(encoding="utf-8"))["paso"], "mirando")

    def test_b1_el_avance_nunca_tumba_una_revision(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(retina.os, "replace", side_effect=PermissionError), \
                mock.patch.object(retina.time, "sleep"):
            retina.anotar_avance(Path(d), "mirando", {})  # no lanza

    def test_b2_si_escribir_el_estado_falla_se_reintenta(self):
        with tempfile.TemporaryDirectory() as d:
            real, intentos = os.replace, []

            def replace(a, b):
                intentos.append(1)
                if len(intentos) < 3:
                    raise PermissionError
                real(a, b)
            with mock.patch.object(app.os, "replace", replace), mock.patch.object(app.time, "sleep"):
                app._escribir_estado(Path(d), estado="listo")
            self.assertEqual(json.loads((Path(d) / "estado.json").read_text(encoding="utf-8"))["estado"], "listo")

    def test_b2_una_revision_que_murio_no_queda_procesando_para_siempre(self):
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "a1b2c3d4e5f6"
            c.mkdir()
            (c / "estado.json").write_text('{"estado": "procesando", "idioma": "en"}', encoding="utf-8")
            viejo = time.time() - 600
            os.utime(c / "estado.json", (viejo, viejo))
            e = app.estado(c)
            self.assertEqual(e["estado"], "error")
            self.assertIn("interrupted", e["mensaje"])

    def test_b2_una_revision_en_marcha_sigue_procesando_aunque_tarde(self):
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "a1b2c3d4e5f6"
            c.mkdir()
            (c / "estado.json").write_text('{"estado": "procesando"}', encoding="utf-8")
            viejo = time.time() - 600
            os.utime(c / "estado.json", (viejo, viejo))
            app._ACTIVAS.add(c.name)
            self.addCleanup(app._ACTIVAS.discard, c.name)
            self.assertEqual(app.estado(c)["estado"], "procesando")

    def test_b2_la_revision_siempre_deja_un_estado_final(self):
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "a1b2c3d4e5f6"
            c.mkdir()
            (c / "video.mp4").write_bytes(b"x")
            with mock.patch.object(retina, "correr", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    app.revisar(c, DATOS_APP, {"modelo": None, "arranque": None, "voz": None})
            self.assertEqual(json.loads((c / "estado.json").read_text(encoding="utf-8"))["estado"], "error")
            self.assertNotIn(c.name, app._ACTIVAS)

    def test_b5_en_el_flujo_publico_se_llega_a_comparando(self):
        with tempfile.TemporaryDirectory() as d:
            c = Path(d)
            (c / "estado.json").write_text('{"estado": "procesando"}', encoding="utf-8")
            (c / app.COMPARAR_CON).write_text("a" * 12, encoding="utf-8")
            for n in ("manifiesto.json", "transcribir.json", "describir.json", "explicar.json"):
                (c / n).write_text("{}", encoding="utf-8")
            app._ACTIVAS.add(c.name)
            self.addCleanup(app._ACTIVAS.discard, c.name)
            self.assertEqual(app.estado(c)["paso"], "comparando")

    def test_q4_un_error_interno_de_valor_no_se_muestra_como_aviso_de_la_persona(self):
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "a1b2c3d4e5f6"
            c.mkdir()
            with mock.patch.object(retina, "correr", side_effect=ValueError("detalle interno: /ruta/secreta")):
                app.revisar(c, DATOS_APP, {"modelo": None, "arranque": None, "voz": None})
            e = json.loads((c / "estado.json").read_text(encoding="utf-8"))
            self.assertNotIn("secreta", e["mensaje"])
            self.assertTrue((c / "error.txt").exists())

    def test_q4_un_aviso_si_se_le_explica_a_la_persona(self):
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "a1b2c3d4e5f6"
            c.mkdir()
            with mock.patch.object(retina, "correr", side_effect=segmentar.Aviso("muy_corto", "x")):
                app.revisar(c, DATOS_APP, {"modelo": None, "arranque": None, "voz": None})
            self.assertIn("5 segundos", json.loads((c / "estado.json").read_text(encoding="utf-8"))["mensaje"])


class Conversion(unittest.TestCase):
    def test_b9_un_webm_sin_duracion_se_convierte_y_se_mide_al_final(self):
        with tempfile.TemporaryDirectory() as d:
            c = Path(d)
            (c / app.SUBIDA).write_bytes(b"x")
            sin_duracion = segmentar.Aviso("no_lee", "No pude leer la duración")

            def convertir(origen, destino):
                destino.write_bytes(b"mp4")
            with mock.patch.object(app, "duracion_s", side_effect=[sin_duracion, 30.0]), mock.patch.object(app, "convertir_a_mp4", side_effect=convertir) as conv, \
                    mock.patch.object(retina, "correr", return_value={}):
                app.revisar(c, DATOS_APP, {"modelo": None, "arranque": None, "voz": None})
            conv.assert_called_once()
            self.assertEqual(json.loads((c / "estado.json").read_text(encoding="utf-8"))["estado"], "listo")

    def test_b9_un_webm_que_resulta_muy_largo_tras_convertir_se_rechaza(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"RETINA_DURACION_MAXIMA_S": "300"}):
            c = Path(d)
            (c / app.SUBIDA).write_bytes(b"x")
            sin_duracion = segmentar.Aviso("no_lee", "x")

            def convertir(origen, destino):
                destino.write_bytes(b"mp4")
            with mock.patch.object(app, "duracion_s", side_effect=[sin_duracion, 4000.0]), mock.patch.object(app, "convertir_a_mp4", side_effect=convertir), \
                    mock.patch.object(retina, "correr") as correr:
                app.revisar(c, DATOS_APP, {"modelo": None, "arranque": None, "voz": None})
            correr.assert_not_called()
            self.assertIn("5 minutos", json.loads((c / "estado.json").read_text(encoding="utf-8"))["mensaje"])

    def test_b9_la_conversion_pide_dimensiones_pares(self):
        with tempfile.TemporaryDirectory() as d, mock.patch("retina.segmentar._ffmpeg", return_value="ffmpeg"), \
                mock.patch.object(app.subprocess, "run") as correr, mock.patch.object(app.os, "replace"):
            correr.return_value = mock.Mock(returncode=0)
            c = Path(d)
            (c / "convirtiendo.mp4").write_bytes(b"x")
            app.convertir_a_mp4(c / "a.webm", c / "video.mp4")
        args = correr.call_args.args[0]
        self.assertIn("trunc(iw/2)*2", args[args.index("-vf") + 1])

    def test_b9_un_webm_solo_con_audio_dice_que_no_trae_imagen(self):
        with tempfile.TemporaryDirectory() as d, mock.patch("retina.segmentar._ffmpeg", return_value="ffmpeg"), \
                mock.patch.object(app.subprocess, "run", return_value=mock.Mock(returncode=1, stderr="")), \
                mock.patch.object(app, "_info", return_value="  Stream #0:0: Audio: opus, 48000 Hz"):
            c = Path(d)
            with self.assertRaises(segmentar.Aviso) as cm:
                app.convertir_a_mp4(c / "a.webm", c / "video.mp4")
        self.assertEqual(cm.exception.clave, "sin_imagen")

    def test_s7_los_tiempos_de_ffmpeg_bajan_y_en_linea_bajan_mas(self):
        self.assertLessEqual(segmentar.tiempo_maximo_s(), 300)
        with mock.patch.dict(os.environ, {"RETINA_FFMPEG_TIEMPO_S": "120"}):
            self.assertEqual(segmentar.tiempo_maximo_s(), 120)
        with mock.patch.dict(os.environ, {"RETINA_FFMPEG_TIEMPO_S": "999999"}):
            self.assertLessEqual(segmentar.tiempo_maximo_s(), 300)

    def test_s7_la_guia_de_despliegue_limita_la_cpu(self):
        guia = (RAIZ / "deploy" / "LEEME-DESPLIEGUE.md").read_text(encoding="utf-8")
        self.assertIn("--cpus", guia)


class Orquestador(unittest.TestCase):
    def test_q3_un_paso_que_falla_deja_su_error_en_un_archivo(self):
        with tempfile.TemporaryDirectory() as d:
            no_pude: list = []
            retina._paso("describir", {}, no_pude, "algo", lambda: 1 / 0, carpeta=Path(d))
            texto = (Path(d) / "error-describir.txt").read_text(encoding="utf-8")
        self.assertIn("ZeroDivisionError", texto)
        self.assertIn("falló: ZeroDivisionError", no_pude[0])

    def test_q6_un_video_muy_corto_o_muy_largo_avisa_que_la_revision_es_gruesa(self):
        corto = retina.avisos_de_tramos({"duracion_s": 5.0, "tramos_sin_cuadros": list(range(19)), "n_tramos": 40})
        self.assertTrue(any("19 de 40" in a for a in corto), corto)
        largo = retina.avisos_de_tramos({"duracion_s": 1800.0, "tramos_sin_cuadros": [], "n_tramos": 40})
        self.assertTrue(any("45" in a for a in largo), largo)
        self.assertEqual(retina.avisos_de_tramos({"duracion_s": 60.0, "tramos_sin_cuadros": [], "n_tramos": 40}), [])

    def test_q5_el_agente_recibe_el_idioma_de_la_tarjeta(self):
        fuente = (RAIZ / "src" / "retina" / "retina.py").read_text(encoding="utf-8")
        self.assertIn("correr_agente, salida, m, cargar_voz(voz), motor, idioma=idioma", fuente.replace("\n", " ").replace("  ", " "))
        from retina import agente
        self.assertIn("inglés", agente.inicio_del_agente({"duracion_s": 30.0}, "en"))
        self.assertNotIn("inglés", agente.inicio_del_agente({"duracion_s": 30.0}, "es"))

    def test_q8_la_transcripcion_local_solo_abre_archivos_locales(self):
        fuente = (RAIZ / "src" / "retina" / "transcribir_local.py").read_text(encoding="utf-8")
        self.assertIn("*PROTOCOLOS", fuente)  # protocol_whitelist y format_whitelist de segmentar


class SamConImagenes(unittest.TestCase):
    def test_un_png_dibujado_se_convierte_en_clip_con_ffmpeg_real(self):
        from retina import sam
        with tempfile.TemporaryDirectory() as d:
            png = Path(d) / "dibujo.png"
            import subprocess
            subprocess.run([segmentar._ffmpeg(), "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64:d=1", "-frames:v", "1", str(png)], check=True)
            clip = sam.clip_de_imagen(png)
            self.assertTrue(clip.is_file() and clip.stat().st_size > 0)
    # Los dibujos de casos/ van en WebP para el repo; los que SAM revisa son los PNG que dibuja Muse Image, cubiertos arriba.

    def test_el_filtro_de_formatos_de_videos_sigue_sin_dejar_pasar_imagenes(self):
        self.assertNotIn("png_pipe", segmentar.PROTOCOLOS[-1])


class DependenciasYPanel(unittest.TestCase):
    def test_q8_cada_dependencia_tiene_version_exacta(self):
        for nombre in ("requirements.txt", "requirements-gpu.txt"):
            for linea in (RAIZ / nombre).read_text(encoding="utf-8").splitlines():
                if linea.strip() and not linea.startswith("#"):
                    with self.subTest(linea=linea):
                        self.assertRegex(linea.strip(), r"^[A-Za-z0-9_.\-]+==\d[\w.]*$")
        self.assertIn("faster-whisper==", (RAIZ / "requirements-gpu.txt").read_text(encoding="utf-8"))

    def test_q8_el_panel_carga_y_sus_ids_existen(self):
        clase = type("Manejador", (demo.SoloElPanel,), {"casos": None})
        servidor = demo.ServidorExclusivo(("127.0.0.1", 0), functools.partial(clase, directory=str(RAIZ)))
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)
        c = http.client.HTTPConnection("127.0.0.1", servidor.server_port, timeout=10)
        c.request("GET", "/panel/", headers={"Host": "127.0.0.1"})
        r = c.getresponse()
        html = r.read().decode("utf-8")
        c.close()
        self.assertEqual(r.status, 200)
        self.assertIn("text/html", r.getheader("Content-Type"))
        self.assertIn("<title>", html)
        ids = set(re.findall(r'\bid="([^"]+)"', html))
        for clave in ("error", "vacio", "subir", "revisando", "resultado", "forma", "revisar", "idioma", "titular", "porque"):
            self.assertIn(clave, ids, clave)
        pedidos = set(re.findall(r"\$\(['\"]([\w-]+)['\"]\)", html)) | set(re.findall(r"getElementById\(['\"]([\w-]+)['\"]\)", html))
        self.assertEqual(sorted(pedidos - ids), [], "el script pide ids que el HTML no tiene")


if __name__ == "__main__":
    unittest.main()
