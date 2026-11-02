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
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from retina import baseten, explicar, meta_api, retina, revision_meta, segmentar, storyboard, traducir  # noqa: E402
from test_candados import ConRegistro  # noqa: E402
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
        self.assertEqual(meta_api.entrada_estimada(cuerpo), entrada)
        self.assertAlmostEqual(meta_api.peor_caso_usd(cuerpo), (1000 * 4.25 + entrada * 1.25) / 1e6, places=9)
        self.assertAlmostEqual(meta_api.peor_caso_usd(cuerpo, entrada_tokens=360_000), (1000 * 4.25 + 360_000 * 1.25) / 1e6, places=9)  # lo declarado ya cuenta su texto
        self.assertEqual(meta_api.entrada_estimada({"model": "muse-spark-1.3"}), 0)

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
        self.assertAlmostEqual(meta_api.reservado_usd(), (1000 * 4.25 + (6000 // meta_api.CARACTERES_POR_TOKEN) * 1.25) / 1e6, places=9)


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
