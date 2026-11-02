"""Lo que una auditoría externa (Codex, 2-nov) encontró y se corrigió: el gasto de cada dibujo se aparta antes de llamar, la
reserva cuenta la entrada, los intocables también se revisan en el storyboard y en lo traducido, el paso del agente acepta
`idioma=`, ffmpeg siempre va por el mismo envoltorio y el destino de la llave se compara por host exacto.

Sin API, sin llaves y sin red: modelos falsos y un registro de costos en una carpeta temporal.
Corren con:  python -m unittest discover -s tests   (desde la raíz del repo)
"""
from __future__ import annotations

import base64
import inspect
import json
import os
import sys
import tempfile
import time
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from retina import baseten, comparar, explicar, meta_api, retina, revision_meta, segmentar, storyboard, traducir  # noqa: E402
from test_candados import TOKENS_20_USD, ConRegistro, FalsoOpenAI, RespuestaFalsa  # noqa: E402
from test_reglas import DATOS, tarjeta  # noqa: E402

PRECIO_DIBUJO = meta_api.PRECIO_IMAGEN[storyboard.MODELO]


class RespuestaDeImagen:
    status_code = 200

    def json(self):
        return {"data": [{"b64_json": base64.b64encode(b"png").decode()}]}


def pedir_imagen_lento(*_a, **_k):
    time.sleep(0.05)  # que las llamadas se traslapen
    return RespuestaDeImagen()


# 1. Cada dibujo aparta su precio con el candado del tope ---------------------------------------------------------

class GastoDeDibujos(ConRegistro):
    def dibujar(self, carpeta: Path, i: int) -> bool:
        try:
            storyboard.dibujar_uno("una escena", carpeta / f"c{i}.png", servicio="apertura")
            return True
        except meta_api.TopeAlcanzado:
            return False

    def test_sin_presupuesto_no_se_llama_a_la_api(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"RETINA_TOPE_USD": str(PRECIO_DIBUJO / 2)}), \
                mock.patch.object(meta_api, "_pedir", pedir_imagen_lento) as pedir:
            self.assertFalse(self.dibujar(Path(d), 1))
        self.assertEqual(len(self.filas()), 0)

    def test_dibujos_a_la_vez_no_pasan_por_el_mismo_hueco(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"RETINA_TOPE_USD": str(PRECIO_DIBUJO * 1.5)}), \
                mock.patch.object(meta_api, "_pedir", pedir_imagen_lento), ThreadPoolExecutor(6) as ex:
            pasaron = list(ex.map(lambda i: self.dibujar(Path(d), i), range(6)))
            self.assertEqual(sum(pasaron), 1, pasaron)  # cabe uno; antes, la comprobación y el cobro iban separados
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), [f"c{i}.png" for i, ok in enumerate(pasaron) if ok])
        self.assertLessEqual(meta_api.gastado_usd(), PRECIO_DIBUJO * 1.5)
        self.assertEqual(len(self.filas()), 1)
        self.assertEqual(meta_api.reservado_usd(), 0)

    def test_un_dibujo_que_la_api_rechaza_suelta_lo_apartado(self):
        malo = mock.Mock(status_code=400, **{"json.return_value": {"error": {"message": "escena rechazada"}}})
        with tempfile.TemporaryDirectory() as d, mock.patch.object(meta_api, "_pedir", return_value=malo), self.assertRaises(RuntimeError):
            storyboard.dibujar_uno("x", Path(d) / "c.png")
        self.assertEqual((meta_api.reservado_usd(), len(self.filas())), (0, 0))

    def test_si_no_sabemos_si_cobro_el_dibujo_se_queda_apartado(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(meta_api, "_pedir", side_effect=ConnectionError("sin red")), \
                self.assertRaises(ConnectionError):
            storyboard.dibujar_uno("x", Path(d) / "c.png")
        self.assertAlmostEqual(meta_api.reservado_usd(), PRECIO_DIBUJO, places=6)

    def test_el_dibujo_de_la_apertura_ya_no_revisa_aparte(self):
        # La revisión previa sin reserva era el hueco: ahora dibujar_uno aparta y dibujar_cuadro no revisa por su cuenta.
        from retina import apertura
        fuente = inspect.getsource(apertura.dibujar_cuadro)
        self.assertNotIn("_revisar_tope", fuente)
        self.assertIn("dibujar_uno", fuente)


# 2. La reserva cuenta lo que se ve de la entrada ----------------------------------------------------------------

class ReservaConEntrada(ConRegistro):
    def test_el_peor_caso_cuenta_el_texto_y_las_imagenes_del_cuerpo(self):
        texto = "x" * 30_000  # unos 10,000 tokens
        cuerpo = {"model": "muse-spark-1.3", "max_output_tokens": 1000,
                  "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": texto}, {"type": "input_image", "image_url": "data:x"}]}]}
        entrada = 30_000 // meta_api.CARACTERES_POR_TOKEN + 1 + meta_api.TOKENS_POR_IMAGEN
        estimada = meta_api.entrada_estimada(cuerpo)
        self.assertGreaterEqual(estimada, entrada)  # el texto y la imagen, más las etiquetas que también viajan
        self.assertLess(estimada, entrada + 50)
        self.assertAlmostEqual(meta_api.peor_caso_usd(cuerpo), (1000 * 4.25 + estimada * 1.25) / 1e6, places=9)
        self.assertAlmostEqual(meta_api.peor_caso_usd(cuerpo, entrada_tokens=360_000), (1000 * 4.25 + 360_000 * 1.25) / 1e6, places=9)  # lo declarado ya cuenta su texto
        self.assertEqual(meta_api.entrada_estimada({"model": "muse-spark-1.3", "max_output_tokens": 100}), 0)

    def test_la_entrada_cuenta_herramientas_sus_argumentos_y_sus_salidas(self):
        base = {"model": "muse-spark-1.3", "max_output_tokens": 100}
        salida = {**base, "input": [{"type": "function_call_output", "call_id": "c1", "output": "y" * 30_000}]}
        argumentos = {**base, "input": [{"type": "function_call", "name": "buscar", "call_id": "c1", "arguments": "w" * 30_000}]}
        herramientas = {**base, "tools": [{"type": "function", "name": "buscar", "description": "z" * 30_000, "parameters": {}}]}
        for cuerpo in (salida, argumentos, herramientas):
            self.assertGreaterEqual(meta_api.entrada_estimada(cuerpo), 10_000, list(cuerpo))

    def test_responder_aparta_la_entrada_aunque_nadie_la_declare(self):
        cuerpo = {"model": "muse-spark-1.3", "max_output_tokens": 100,
                  "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "x" * 3_000_000}]}]}  # ~1 millón de tokens: USD 1.25
        with mock.patch.dict(os.environ, {"RETINA_TOPE_USD": "1"}), mock.patch.object(meta_api, "_pedir") as pedir, \
                self.assertRaises(meta_api.TopeAlcanzado):
            meta_api.responder("prueba", cuerpo)
        pedir.assert_not_called()

    def test_baseten_aparta_tambien_la_entrada(self):
        mensajes = [{"role": "system", "content": "a" * 3000}, {"role": "user", "content": "b" * 3000}]
        reserva = baseten._reservar("prueba", 1000, mensajes)
        self.addCleanup(meta_api.liberar, reserva)
        minimo = (1000 * 4.25 + (6000 // meta_api.CARACTERES_POR_TOKEN) * 1.25) / 1e6
        self.assertGreaterEqual(meta_api.reservado_usd(), minimo)
        self.assertLess(meta_api.reservado_usd(), minimo * 1.1)

    def test_baseten_cuenta_llamadas_y_definiciones_de_herramientas(self):
        con_llamada = [{"role": "assistant", "content": None, "tool_calls": [{"id": "1", "type": "function", "function": {"name": "buscar", "arguments": "q" * 30_000}}]}]
        herramientas = [{"type": "function", "function": {"name": "buscar", "description": "d" * 30_000}}]
        for mensajes, tools in ((con_llamada, None), ([{"role": "user", "content": "hola"}], herramientas)):
            reserva = baseten._reservar("prueba", 1000, mensajes, tools)
            self.assertGreaterEqual(meta_api.reservado_usd(), (1000 * 4.25 + 10_000 * 1.25) / 1e6)
            meta_api.liberar(reserva)


# 2b. Cada intento que pudo cobrarse aparta lo suyo ------------------------------------------------------------

class CadaIntentoApartaLoSuyo(ConRegistro):
    def respuestas(self, *estados):
        cola = iter([RespuestaFalsa(1000) if e == 200 else mock.Mock(status_code=e, headers={}) for e in estados])
        return mock.patch.object(meta_api.requests, "request", side_effect=lambda *a, **k: next(cola))

    def test_un_5xx_deja_apartado_su_intento_y_el_siguiente_aparta_otro(self):
        cuerpo = {"model": "muse-spark-1.3", "max_output_tokens": 1000}
        peor = meta_api.peor_caso_usd(cuerpo)
        with self.respuestas(500, 502, 200) as pedir, mock.patch.object(meta_api.time, "sleep"):
            meta_api.responder("prueba", cuerpo)
        self.assertEqual(pedir.call_count, 3)
        self.assertEqual(len(self.filas()), 1)
        self.assertAlmostEqual(meta_api.reservado_usd(), 2 * peor, places=9)  # los dos intentos que pudieron cobrarse se quedan apartados

    def test_un_429_se_repite_sin_apartar_otro(self):
        cuerpo = {"model": "muse-spark-1.3", "max_output_tokens": 1000}
        with self.respuestas(429, 200) as pedir, mock.patch.object(meta_api.time, "sleep"):
            meta_api.responder("prueba", cuerpo)
        self.assertEqual((pedir.call_count, len(self.filas()), meta_api.reservado_usd()), (2, 1, 0))

    def test_sin_presupuesto_para_repetir_no_se_repite(self):
        cuerpo = {"model": "muse-spark-1.3", "max_output_tokens": TOKENS_20_USD}  # 20 USD por intento con tope de 50: caben dos
        with self.respuestas(500, 500, 200) as pedir, mock.patch.object(meta_api.time, "sleep"), self.assertRaises(meta_api.TopeAlcanzado):
            meta_api.responder("prueba", cuerpo)
        self.assertEqual((pedir.call_count, len(self.filas())), (2, 0))

    def test_tres_5xx_dejan_apartados_los_tres_intentos(self):
        cuerpo = {"model": "muse-spark-1.3", "max_output_tokens": 1000}
        with self.respuestas(500, 500, 503) as pedir, mock.patch.object(meta_api.time, "sleep"), self.assertRaises(RuntimeError):
            meta_api.responder("prueba", cuerpo)
        self.assertEqual((pedir.call_count, len(self.filas())), (3, 0))
        self.assertAlmostEqual(meta_api.reservado_usd(), 3 * meta_api.peor_caso_usd(cuerpo), places=9)  # ninguno se sabe si cobró

    def test_un_5xx_y_luego_un_4xx_deja_apartado_solo_el_incierto(self):
        cuerpo = {"model": "muse-spark-1.3", "max_output_tokens": 1000}
        with self.respuestas(500, 400) as pedir, mock.patch.object(meta_api.time, "sleep"), self.assertRaises(RuntimeError):
            meta_api.responder("prueba", cuerpo)
        self.assertEqual((pedir.call_count, len(self.filas())), (2, 0))
        self.assertAlmostEqual(meta_api.reservado_usd(), meta_api.peor_caso_usd(cuerpo), places=9)  # el 400 no cobró; el 500 no se sabe

    def test_un_dibujo_tambien_aparta_por_intento(self):
        cola = iter([mock.Mock(status_code=500, headers={}), mock.Mock(status_code=502, headers={}), RespuestaDeImagen()])
        with tempfile.TemporaryDirectory() as d, mock.patch.object(meta_api.requests, "request", side_effect=lambda *a, **k: next(cola)) as pedir, \
                mock.patch.object(meta_api.time, "sleep"):
            storyboard.dibujar_uno("una escena", Path(d) / "c.png")
            self.assertTrue((Path(d) / "c.png").is_file())
        self.assertEqual((pedir.call_count, len(self.filas())), (3, 1))
        self.assertAlmostEqual(meta_api.reservado_usd(), 2 * PRECIO_DIBUJO, places=9)

    def test_la_transcripcion_tambien_aparta_por_intento(self):
        buena = mock.Mock(status_code=200, **{"json.return_value": {"audioDurationMs": 60_000}})
        cola = iter([mock.Mock(status_code=500, headers={}), mock.Mock(status_code=500, headers={}), buena])
        with tempfile.TemporaryDirectory() as d, mock.patch.object(meta_api.requests, "request", side_effect=lambda *a, **k: next(cola)) as pedir, \
                mock.patch.object(meta_api.time, "sleep"):
            wav = Path(d) / "a.wav"
            wav.write_bytes(b"RIFF" + b"\0" * 100)
            meta_api.transcribir_wav(wav)
        self.assertEqual((pedir.call_count, len(self.filas())), (3, 1))
        self.assertAlmostEqual(meta_api.reservado_usd(), 2 * meta_api.PRECIO_HORA_AUDIO["muse-voice-transcribe-1.0"] * 10 / 60, places=9)


class FalsoOpenAIQueFalla(FalsoOpenAI):
    fallos: list = []  # lo que lanza antes de contestar bien

    def create(self, **kw):
        if FalsoOpenAIQueFalla.fallos:
            raise FalsoOpenAIQueFalla.fallos.pop(0)
        return super().create(**kw)


class BasetenApartaCadaIntento(ConRegistro):
    MENSAJES = [{"role": "user", "content": "hola"}]

    def setUp(self):
        super().setUp()
        for parche in (mock.patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=FalsoOpenAIQueFalla)}),
                       mock.patch.object(baseten.time, "sleep")):
            parche.start()
            self.addCleanup(parche.stop)
        FalsoOpenAIQueFalla.fallos = []

    @staticmethod
    def error(estado: int) -> Exception:
        return type("ErrorDeApi", (Exception,), {"status_code": estado})("falló")

    def uno(self) -> float:
        r = baseten._reservar("prueba", 1000, self.MENSAJES)
        try:
            return meta_api.reservado_usd()
        finally:
            meta_api.liberar(r)

    def test_dos_5xx_y_luego_bien_dejan_apartados_los_dos_intentos(self):
        uno = self.uno()
        FalsoOpenAIQueFalla.fallos = [self.error(500), self.error(503)]
        baseten.completar("prueba", self.MENSAJES, 1000)
        self.assertEqual(len(self.filas()), 1)
        self.assertAlmostEqual(meta_api.reservado_usd(), 2 * uno, places=9)

    def test_un_429_se_repite_sin_apartar_otro(self):
        FalsoOpenAIQueFalla.fallos = [self.error(429)]
        baseten.completar("prueba", self.MENSAJES, 1000)
        self.assertEqual((len(self.filas()), meta_api.reservado_usd()), (1, 0))

    def test_un_400_suelta_todo_y_no_se_repite(self):
        FalsoOpenAIQueFalla.fallos = [self.error(400)]
        with self.assertRaises(Exception):
            baseten.completar("prueba", self.MENSAJES, 1000)
        self.assertEqual((len(self.filas()), meta_api.reservado_usd()), (0, 0))

    def test_sin_respuesta_tres_veces_todo_se_queda_apartado(self):
        uno = self.uno()
        FalsoOpenAIQueFalla.fallos = [ConnectionError("sin red")] * 3
        with self.assertRaises(ConnectionError):
            baseten.completar("prueba", self.MENSAJES, 1000)
        self.assertAlmostEqual(meta_api.reservado_usd(), 3 * uno, places=9)

    def test_un_5xx_y_luego_un_4xx_deja_apartado_solo_el_incierto(self):
        uno = self.uno()
        FalsoOpenAIQueFalla.fallos = [self.error(500), self.error(400)]
        with self.assertRaises(Exception):
            baseten.completar("prueba", self.MENSAJES, 1000)
        self.assertEqual(len(self.filas()), 0)
        self.assertAlmostEqual(meta_api.reservado_usd(), uno, places=9)  # el 400 no cobró; el 500 no se sabe


# 7. Las imágenes de Docker llevan las licencias ------------------------------------------------------------------

class DockerConLicencias(unittest.TestCase):
    def test_cada_imagen_copia_sus_licencias(self):
        demo = (RAIZ / "deploy" / "Dockerfile").read_text(encoding="utf-8")
        en_linea = (RAIZ / "deploy" / "Dockerfile.en-linea").read_text(encoding="utf-8")
        for archivo in ("LICENSE", "NOTICE"):
            self.assertRegex(demo, rf"(?m)^COPY .*\b{archivo}\b", archivo)
            self.assertRegex(en_linea, rf"(?m)^COPY .*\b{archivo}\b", archivo)
        self.assertRegex(en_linea, r"(?m)^COPY .*LICENSE-MUSE\.md")  # los pesos van en esa imagen: su licencia también
        self.assertNotIn("LICENSE-MUSE", demo)  # la demo estática no lleva pesos


# 3. Los intocables se revisan en todo lo que se va a editar ----------------------------------------------------

class IntocablesEnTodoElRecorrido(unittest.TestCase):
    def test_el_storyboard_no_puede_tocar_un_intocable(self):
        self.assertTrue(explicar.toca_intocable("Quita el logo del video."))  # la regla existe
        problemas = explicar.revisar(tarjeta(storyboard=["Quita el logo del video.", "Un perro al centro", "Una mesa"]), DATOS)
        self.assertTrue(any("cuadro 1 del storyboard toca algo intocable" in p for p in problemas), problemas)
        self.assertEqual(explicar.revisar(tarjeta(storyboard=["Un perro al centro", "Una mano revisa una oreja", "Una mesa"]), DATOS), [])

    def test_la_traduccion_no_puede_agregar_un_intocable(self):
        self.assertTrue(explicar.toca_intocable("Remove the logo from the video."))
        self.assertFalse(traducir.sin_inventar("Corta el saludo del video.", "Remove the logo from the video."))
        self.assertFalse(traducir.aceptable("Corta el saludo del video.", "Remove the logo from the video."))
        self.assertTrue(traducir.aceptable("Corta el saludo del video.", "Cut the greeting from the video."))

    def test_el_generador_suelto_de_storyboard_tambien_frena_un_intocable(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(storyboard, "dibujar_uno") as dibujar, mock.patch.object(meta_api, "_revisar_tope"):
            e = Path(d) / "explicar.json"
            e.write_text(json.dumps({"storyboard": ["Quita el logo del video.", "Un perro al centro", "Una mesa"]}), encoding="utf-8")
            with self.assertRaises(RuntimeError) as cm:
                storyboard.generar(e, [], aprobar=True)
            self.assertIn("intocable", str(cm.exception))
            dibujar.assert_not_called()
            e.write_text(json.dumps({"storyboard": ["Una bolsa de pan cerrada, sin logos.", "Un perro al centro", "Una mesa"]}), encoding="utf-8")
            self.assertEqual(len(storyboard.generar(e, [], aprobar=True)), 3)  # «sin logos» es el estilo de la casa


# 3b. Una traducción no puede volver recomendación lo que se manda quitar ------------------------------------

class TraduccionQueInvierte(unittest.TestCase):
    def test_la_cita_que_se_manda_quitar_sigue_mandándose_quitar(self):
        self.assertFalse(traducir.sin_inventar("Corta «Comenta abajo».", "Say «Comenta abajo»."))
        self.assertFalse(traducir.aceptable("Corta «Comenta abajo».", "Say «Comenta abajo»."))
        self.assertTrue(traducir.aceptable("Corta «Comenta abajo».", "Cut «Comenta abajo»."))
        self.assertTrue(traducir.aceptable("Quita el saludo del segundo 2.", "Remove the greeting at second 2."))

    def test_que_citas_se_mandan_quitar(self):
        quitar = traducir._citas_a_quitar("Corta «Comenta abajo» y di «hola».")
        self.assertIn(explicar._sin_signos("Comenta abajo"), quitar)
        self.assertNotIn(explicar._sin_signos("hola"), quitar)  # tiene otra orden en medio: no es una cita que se quita
        self.assertEqual(traducir._citas_a_quitar("Say «Comenta abajo»."), frozenset())


# 3c. Una diferencia solo se sostiene con el mismo aspecto en los dos órdenes ---------------------------------

class ParejasPorNombre(unittest.TestCase):
    def test_sin_el_mismo_aspecto_no_hay_pareja(self):
        self.assertIsNone(comparar._pareja({"aspecto": "Encuadre"}, [{"aspecto": "Voz", "mejor": "A"}]))
        self.assertEqual(comparar._pareja({"aspecto": "Voz en off"}, [{"aspecto": "Voz", "mejor": "A"}])["aspecto"], "Voz")

    def test_una_diferencia_sin_pareja_no_sostiene_a_la_ganadora(self):
        ab = {"mejor": "A", "por_que": "A arranca mejor.", "diferencias": [{"aspecto": "Encuadre", "a": "x", "b": "y", "mejor": "A"}]}
        ba = {"mejor": "A", "por_que": "A arranca mejor.", "diferencias": [{"aspecto": "Voz", "a": "x", "b": "y", "mejor": "A"}]}
        s = comparar.combinar(ab, ba)
        self.assertEqual([d["mejor"] for d in s["diferencias"]], ["igual"])
        self.assertEqual(s["veredicto"], "empate")


# 4. El paso del agente acepta argumentos por nombre ------------------------------------------------------------

class PasoConIdioma(unittest.TestCase):
    def test_paso_reenvia_lo_que_llega_por_nombre(self):
        tiempos, no_pude = {}, []
        salida = retina._paso("agente", tiempos, no_pude, "qué", lambda carpeta, idioma="es": (carpeta, idioma), "c", idioma="en")
        self.assertEqual((salida, no_pude, list(tiempos)), (("c", "en"), [], ["agente"]))

    def test_la_rama_del_agente_pasa_el_idioma_por_nombre(self):
        # Antes, paso() solo aceptaba posicionales y esta rama fallaba con TypeError antes de llegar al agente.
        fuente = inspect.getsource(retina.correr)
        self.assertIn("def paso(nombre: str, que: str, funcion, *args, **kwargs):", fuente)
        self.assertIn("correr_agente, salida, m, cargar_voz(voz), motor, idioma=idioma)", fuente)


# 5. Todo ffmpeg pasa por el mismo envoltorio --------------------------------------------------------------------

class ProporcionConCandados(unittest.TestCase):
    def test_la_proporcion_se_lee_con_el_envoltorio_de_segmentar(self):
        info = "Input #0\n  Stream #0:0: Video: h264 (High), yuv420p, 1080x1920, 30 fps\n"
        with mock.patch.object(segmentar, "_info", return_value=info) as leer:
            self.assertAlmostEqual(revision_meta._proporcion(Path("x.mp4")), 1080 / 1920)
        leer.assert_called_once_with(Path("x.mp4"))
        self.assertFalse(hasattr(revision_meta, "subprocess"))  # sin llamadas propias a ffmpeg

    def test_si_ffmpeg_no_contesta_a_tiempo_no_hay_proporcion(self):
        with mock.patch.object(segmentar, "_info", side_effect=segmentar.Aviso("no_lee", "tardó")):
            self.assertIsNone(revision_meta._proporcion(Path("x.mp4")))


# 6. La llave solo sale a Meta o a este equipo, por host exacto ------------------------------------------------

class DestinoDeLaLlave(unittest.TestCase):
    def base(self, url: str) -> str:
        with mock.patch.dict(os.environ, {"META_API_BASE": url}), mock.patch.object(meta_api, "_cargar_env"):
            return meta_api.base()

    def test_acepta_meta_y_lo_local(self):
        for url in ("https://api.meta.ai/v1", "http://127.0.0.1:8080/v1", "http://localhost/v1", "http://localhost:9000"):
            self.assertEqual(self.base(url), url)

    def test_rechaza_lo_que_solo_empieza_igual(self):
        for url in ("http://localhost.ejemplo.invalid/v1", "https://api.meta.ai.evil.com/v1", "http://127.0.0.1.evil.com/v1",
                    "https://user:pw@api.meta.ai/v1", "https://api.meta.ai/v1#x", "http://api.meta.ai/v1", "https://localhost/v1",
                    "ftp://api.meta.ai/v1", "api.meta.ai/v1", "https://evil.com/?u=https://api.meta.ai/"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.base(url)


if __name__ == "__main__":
    unittest.main()
