"""La apertura arreglada: reglas de texto, comprobación con SAM, correcciones y lo que nunca llega a la persona.

Sin API, sin llaves y sin red: el modelo, Muse Image y SAM son funciones falsas.
Corren con:  python -m unittest discover -s tests   (desde la raíz del repo)
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from retina import apertura, app, meta_api, storyboard  # noqa: E402

TITULO = "Tres trucos para que el pan dulce no se endurezca"
DATOS = {"titulo": TITULO, "fuente": "tres trucos para que el pan dulce no se endurezca lleva 2 horas en bolsa de tela con Doña Rosa"}
VOZ = ("Tu pan dulce no se endurece si lo guardas bien. Lo metes en una bolsa de tela, lo dejas 2 horas y mañana "
       "sigue suave. Estos son los tres trucos que lo mantienen fresco toda la semana.")
CUADROS = ["Una pieza de pan dulce suave junto a una dura.", "Una bolsa de tela sobre la mesa.", "Una canasta con pan fresco."]


def buena(**cambios) -> dict:
    return {"voz": VOZ, "cuadros": list(CUADROS), **cambios}


def ids(s, datos=DATOS) -> list[str]:
    return [p["id"] for p in apertura.revisar(s, datos)]


class ReglasDeTexto(unittest.TestCase):
    def test_una_apertura_buena_pasa(self):
        self.assertEqual(ids(buena()), [])

    def test_un_anzuelo_en_la_voz_se_rechaza(self):
        self.assertIn("anzuelos", ids(buena(voz=VOZ + " Comenta si te pasó.")))

    def test_un_anzuelo_en_un_cuadro_tambien(self):
        self.assertIn("anzuelos", ids(buena(cuadros=[CUADROS[0], "Un cartel que dice comenta abajo.", CUADROS[2]])))

    def test_no_puede_cambiar_algo_intocable(self):
        self.assertIn("intocables", ids(buena(voz=VOZ + " Quita el aviso legal del final.")))

    def test_una_cifra_que_no_viene_del_video_se_rechaza(self):
        self.assertIn("cifras", ids(buena(voz=VOZ.replace("2 horas", "7 horas"))))

    def test_una_cifra_con_letra_que_no_viene_del_video_se_rechaza(self):
        self.assertIn("cifras", ids(buena(voz=VOZ.replace("2 horas", "veinte horas"))))

    def test_una_cifra_del_video_si_pasa_aunque_venga_con_letra_en_el_titulo(self):
        self.assertEqual(ids(buena(voz=VOZ.replace("tres trucos", "3 trucos"))), [])

    def test_una_fecha_o_una_lista_de_cifras_no_truena_el_revisor(self):
        fuente = "el 30.10.2026 y las cifras 1,2,3"
        self.assertEqual(apertura.cifras_nuevas("El 30.10.2026 y las cifras 1,2,3.", fuente), [])
        self.assertEqual(apertura.cifras_nuevas("El 31.10.2026.", fuente), ["31"])

    def test_los_miles_valen_con_coma_con_punto_o_sin_nada(self):
        self.assertEqual(apertura.cifras_nuevas("Son 1,000 pesos y 2.500 más.", "1000 pesos y 2500 mas"), [])

    def test_un_nombre_que_no_viene_del_video_se_rechaza(self):
        self.assertIn("nombres", ids(buena(voz=VOZ + " Lo cuenta Martha Sánchez.")))

    def test_un_nombre_del_video_si_pasa(self):
        self.assertEqual(ids(buena(voz=VOZ.replace("Estos son", "Doña Rosa enseña"))), [])

    def test_el_tema_del_titulo_va_en_la_primera_frase(self):
        self.assertIn("tema", ids(buena(voz="Esto casi nadie lo hace bien. " + VOZ)))

    def test_el_tema_acepta_otra_terminacion_de_la_palabra(self):
        self.assertEqual(ids(buena(voz="Los panes dulces duran más. " + VOZ.split(". ", 1)[1])), [])

    def test_un_titulo_de_trabajo_no_obliga_a_decir_sus_palabras(self):
        datos = {"titulo": "VERSION 1", "fuente": DATOS["fuente"]}
        self.assertNotIn("tema", ids(buena(voz="Esto casi nadie lo hace bien. " + VOZ), datos))

    def test_una_voz_muy_corta_o_muy_larga_se_rechaza(self):
        self.assertIn("largo", ids(buena(voz="Tu pan dulce no se endurece.")))
        self.assertIn("largo", ids(buena(voz=VOZ + " " + VOZ)))

    def test_tienen_que_ser_tres_cuadros_con_algo_escrito(self):
        self.assertIn("cuadros", ids(buena(cuadros=CUADROS[:2])))
        self.assertIn("cuadros", ids(buena(cuadros=[CUADROS[0], " ", CUADROS[2]])))

    def test_una_respuesta_sin_el_formato_se_rechaza_sin_tronar(self):
        self.assertIn("formato", ids({"voz": 3}))


class Lazo(unittest.TestCase):
    def correr(self, respuestas, medidas=(), concepto="bread"):
        self.pedidos, self.dibujos = [], []
        respuestas, medidas = iter(respuestas), iter(medidas)

        def pedir(datos, aviso):
            self.pedidos.append(aviso)
            r = next(respuestas)
            if isinstance(r, Exception):
                raise r
            return r

        def dibujar(i, cuadro, objeto):
            self.dibujos.append((i, objeto))
            return Path(f"apertura-cuadro{i}-ilustracion-ia.png")

        self.medir = mock.Mock(side_effect=lambda imagen, c: next(medidas))
        return apertura.lazo(DATOS, concepto, pedir, dibujar, self.medir)

    SE_VE = {"concepto": "bread", "aparece": True, "primer_segundo": 0.0}
    NO_SE_VE = {"concepto": "bread", "aparece": False, "primer_segundo": None}

    def test_pasa_a_la_primera_y_dibuja_los_tres_cuadros(self):
        r = self.correr([buena()], [self.SE_VE])
        self.assertTrue(r["aprobada"])
        self.assertEqual(r["vueltas"], 0)
        self.assertEqual([i for i, _ in self.dibujos], [1, 2, 3])
        self.assertEqual(self.dibujos[0][1], "bread")
        self.assertEqual(len(r["despues"]["imagenes"]), 3)
        self.assertEqual({c["id"]: c["paso"] for c in r["comprobaciones"]}["promesa"], True)

    def test_si_sam_no_ve_la_promesa_se_corrige_diciendole_que_fallo(self):
        r = self.correr([buena(), buena()], [self.NO_SE_VE, self.SE_VE])
        self.assertTrue(r["aprobada"])
        self.assertEqual(r["vueltas"], 1)
        self.assertIn("bread", self.pedidos[1])
        self.assertEqual(len(r["intentos"]), 2)

    def test_la_promesa_tiene_que_verse_desde_el_primer_cuadro(self):
        tarde = {**self.SE_VE, "primer_segundo": 1.2}
        r = self.correr([buena(), buena()], [tarde, self.SE_VE])
        self.assertEqual(r["vueltas"], 1)

    def test_si_el_texto_falla_no_se_gasta_en_dibujar(self):
        r = self.correr([buena(voz=VOZ + " Comenta si te pasó."), buena()], [self.SE_VE])
        self.assertTrue(r["aprobada"])
        self.assertEqual([i for i, _ in self.dibujos], [1, 2, 3])
        self.medir.assert_called_once()

    def test_con_dos_correcciones_sin_exito_nada_del_modelo_llega_a_la_persona(self):
        mala = buena(voz=VOZ + " Comenta si te pasó.")
        r = self.correr([mala, mala, mala])
        self.assertFalse(r["aprobada"])
        self.assertIsNone(r["despues"])
        self.assertEqual(len(r["intentos"]), 3)
        self.assertEqual(self.dibujos, [])
        self.assertNotIn("Comenta si te pasó", json.dumps(r, ensure_ascii=False))
        self.assertFalse({c["id"]: c["paso"] for c in r["comprobaciones"]}["anzuelos"])

    def test_sin_promesa_visible_no_se_llama_a_sam(self):
        r = self.correr([buena()], concepto=None)
        self.assertTrue(r["aprobada"])
        self.medir.assert_not_called()
        self.assertIsNone(self.dibujos[0][1])
        self.assertNotIn("promesa", {c["id"] for c in r["comprobaciones"]})

    def test_una_respuesta_rota_gasta_un_intento_y_sigue(self):
        r = self.correr([RuntimeError("sin JSON"), buena()], [self.SE_VE])
        self.assertTrue(r["aprobada"])
        self.assertEqual(r["vueltas"], 1)

    def test_si_sam_no_contesta_no_se_presume_la_comprobacion(self):
        r = self.correr([buena()], [{"concepto": "bread", "error": "SAM no terminó"}])
        self.assertTrue(r["aprobada"])
        self.assertNotIn("promesa", {c["id"] for c in r["comprobaciones"]})
        self.assertTrue(r["no_comprobe"])

    def test_el_tope_de_gasto_detiene_todo(self):
        with self.assertRaises(meta_api.TopeAlcanzado):
            self.correr([meta_api.TopeAlcanzado("tope")])


class PedirASparkOpen(unittest.TestCase):
    def test_la_lista_de_lo_que_fallo_y_los_datos_llegan_al_modelo_pero_no_la_fuente(self):
        with mock.patch.object(apertura.baseten, "chat", return_value=json.dumps(buena())) as chat:
            self.assertEqual(apertura.pedir(DATOS, "la voz mide 3 palabras"), buena())
        sistema, usuario = chat.call_args.args[1]
        self.assertIn("FORMATO DE RESPUESTA", sistema["content"])
        self.assertIn("la voz mide 3 palabras", usuario["content"])
        self.assertIn(TITULO, usuario["content"])
        self.assertNotIn("fuente", usuario["content"])

    def test_si_gasta_la_salida_pensando_se_repite_con_mas_espacio_y_luego_avisa(self):
        with mock.patch.object(apertura.baseten, "chat", return_value="") as chat, self.assertRaises(RuntimeError):
            apertura.pedir(DATOS)
        self.assertEqual([c.kwargs["max_tokens"] for c in chat.call_args_list], [8000, 14000])


class Rehacer(unittest.TestCase):
    def preparar(self, d: Path, resultado: dict | None = None) -> None:
        (d / "manifiesto.json").write_text(json.dumps({"duracion_s": 96.0, "tramos": [
            {"inicio_s": i * 2.4, "fin_s": (i + 1) * 2.4} for i in range(40)]}), encoding="utf-8")
        (d / "describir.json").write_text(json.dumps({"tramos": [
            {"tramo": i, "que_pasa": "Una mesa con pan.", "texto_en_pantalla": "Lleva 5 pasos", "tipo_de_plano": "plano_medio",
             "cambio_de_plano": False, "presentador_en_pantalla": False, "tipo_de_gancho": "ninguno"} for i in range(40)]}), encoding="utf-8")
        (d / "transcribir.json").write_text(json.dumps({"arranque_voz_ms": 0, "silencios": [], "turnos": [
            {"startMs": 1000, "transcript": "Hola, soy Rosa y hoy te cuento del pan."},
            {"startMs": 90000, "transcript": "Y dura 9 días."}]}), encoding="utf-8")
        (d / "resultado.json").write_text(json.dumps(resultado or {"video": {"titulo": TITULO}, "arranque": {"nivel": "sin_nivel"}}),
                                          encoding="utf-8")

    def test_lo_dicho_al_final_del_video_tambien_cuenta_como_fuente(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t); self.preparar(d)
            datos = apertura.datos_de_apertura(d, TITULO, "es")
        self.assertIn("9 dias", datos["fuente"])
        self.assertIn("5 pasos", datos["fuente"])
        self.assertIn("Y dura 9 días.", datos["resto_de_lo_que_se_dice"])
        self.assertNotIn("nivel_de_riesgo", datos)

    def test_el_idioma_sale_del_video_y_no_del_panel(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t); self.preparar(d)
            self.assertEqual(apertura.datos_de_apertura(d, TITULO, "en")["idioma_de_la_apertura"], "español")

    def test_queda_anotada_en_el_resultado_con_el_titulo_intacto(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(apertura.sam, "objeto_del_titulo", return_value=None), \
                mock.patch.object(apertura, "pedir", return_value=buena(voz=VOZ.replace("2 horas", "5 pasos"))), \
                mock.patch.object(apertura, "dibujar_cuadro",
                                  side_effect=lambda c, i, texto, o: c / f"apertura-cuadro{i}-ilustracion-ia.png"):
            d = Path(t); self.preparar(d)
            salida = apertura.rehacer(d)
            r = json.loads((d / "resultado.json").read_text(encoding="utf-8"))
        self.assertTrue(salida["aprobada"], salida["intentos"])
        self.assertEqual(r["apertura"]["titulo"], TITULO)
        self.assertEqual(r["video"]["titulo"], TITULO)
        self.assertIn("Hola, soy Rosa", r["apertura"]["antes"]["voz"])
        self.assertEqual(r["apertura"]["licencia"]["dibujo"], storyboard.MODELO)

    def test_el_antes_no_se_alarga_mas_que_el_despues(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            antes = apertura.antes_del_cambio(d, {"frases": [{"segundo": 1.0, "dice": " ".join(["palabra"] * 100)}]})
        self.assertEqual(len(antes["voz"].split()), apertura.MAX_PALABRAS)
        self.assertTrue(antes["voz"].endswith("…"))

    def test_si_cambia_el_video_de_la_carpeta_la_apertura_vieja_se_borra(self):
        from retina.retina import preparar_carpeta
        with tempfile.TemporaryDirectory() as t:
            d = Path(t); video = d / "v.mp4"
            video.write_bytes(b"uno"); preparar_carpeta(video, d)
            (d / "apertura.json").write_text("{}", encoding="utf-8")
            video.write_bytes(b"dos"); preparar_carpeta(video, d)
            self.assertFalse((d / "apertura.json").exists())

    def test_no_se_paga_dos_veces_por_la_misma_revision(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(apertura, "pedir", side_effect=AssertionError("pagó")):
            d = Path(t); self.preparar(d)
            (d / "apertura.json").write_text(json.dumps({"aprobada": True}), encoding="utf-8")
            self.assertEqual(apertura.rehacer(d), {"aprobada": True})

    def test_el_primer_cuadro_le_pide_a_muse_image_el_objeto_prometido(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(storyboard, "dibujar_uno") as dibujar:
            apertura.dibujar_cuadro(Path(t), 1, "Una mesa de cocina.", "bread")
            apertura.dibujar_cuadro(Path(t), 2, "Una bolsa.", None)
        primero, segundo = dibujar.call_args_list[0].args[0], dibujar.call_args_list[1].args[0]
        self.assertIn("bread", primero)
        self.assertNotIn("bread", segundo)


class SinLlaveDeBaseten(unittest.TestCase):
    def test_con_solo_la_llave_de_meta_escribe_muse_spark_1_3(self):
        respuesta = {"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(buena())}]}]}
        with mock.patch.dict(apertura.os.environ, {"BASETEN_API_KEY": ""}), mock.patch.object(meta_api, "_cargar_env"), \
                mock.patch.object(apertura.baseten, "chat", side_effect=AssertionError("usó Baseten")), \
                mock.patch.object(meta_api, "responder", return_value=respuesta) as responder:
            self.assertEqual(apertura.pedir(DATOS), buena())
            self.assertEqual(apertura.quien_escribe(), (apertura.explicar.MODELO, "Meta Model API"))
        self.assertNotIn("fuente", json.dumps(responder.call_args.args[1]["input"][1], ensure_ascii=False))

    def test_con_llave_de_baseten_escribe_muse_spark_open(self):
        with mock.patch.dict(apertura.os.environ, {"BASETEN_API_KEY": "x"}), mock.patch.object(meta_api, "_cargar_env"):
            self.assertEqual(apertura.quien_escribe(), (apertura.baseten.MODELO, "Baseten"))


class DesdeLaApp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.carpeta = Path(self.tmp.name) / "abcdef123456"
        self.carpeta.mkdir()
        (self.carpeta / "resultado.json").write_text("{}", encoding="utf-8")
        self.fila = mock.Mock()
        self.addCleanup(app._APERTURAS.clear)
        lista = {"ffmpeg": True, "llave": True}
        for parche in (mock.patch.object(app, "salud", return_value=lista),):
            parche.start()
            self.addCleanup(parche.stop)

    def test_sin_revision_no_hay_nada_que_arreglar(self):
        codigo, _ = app.pedir_apertura(self.carpeta.parent / "no-existe", self.fila, "es")
        self.assertEqual(codigo, 404)
        self.fila.submit.assert_not_called()

    def test_dos_clics_forman_una_sola_apertura(self):
        self.assertEqual(app.pedir_apertura(self.carpeta, self.fila, "es")[0], 202)
        self.assertEqual(app.pedir_apertura(self.carpeta, self.fila, "es")[0], 202)
        self.fila.submit.assert_called_once()

    def test_la_que_ya_esta_hecha_no_se_vuelve_a_pagar(self):
        (self.carpeta / "apertura.json").write_text("{}", encoding="utf-8")
        self.assertEqual(app.pedir_apertura(self.carpeta, self.fila, "es"), (200, {"estado": "listo"}))
        self.fila.submit.assert_not_called()

    def test_sin_llave_se_avisa_en_el_idioma_del_panel(self):
        with mock.patch.object(app, "salud", return_value={"ffmpeg": True, "llave": False}):
            codigo, cuerpo = app.pedir_apertura(self.carpeta, self.fila, "en")
        self.assertEqual(codigo, 503)
        self.assertIn("key is missing", cuerpo["error"])

    def test_el_avance_se_ve_mientras_corre_y_se_limpia_al_terminar(self):
        visto = []

        def rehacer(carpeta, idioma, avisar):
            avisar("buscando", 1)
            visto.append(app.estado_apertura(carpeta))
            (carpeta / "apertura.json").write_text("{}", encoding="utf-8")

        with mock.patch.object(apertura, "rehacer", rehacer):
            app.arreglar(self.carpeta, "es")
        self.assertEqual(visto, [{"estado": "procesando", "paso": "buscando", "vuelta": 1}])
        self.assertEqual(app.estado_apertura(self.carpeta), {"estado": "listo"})

    def test_el_tope_se_explica_y_se_puede_reintentar(self):
        with mock.patch.object(apertura, "rehacer", side_effect=meta_api.TopeAlcanzado("tope de 50")):
            app.arreglar(self.carpeta, "es")
        e = app.estado_apertura(self.carpeta)
        self.assertEqual(e["estado"], "error")
        self.assertIn("tope", e["mensaje"])
        self.assertEqual(app.pedir_apertura(self.carpeta, self.fila, "es")[0], 202)

    def test_otra_falla_va_a_un_archivo_sin_detalles_para_la_persona(self):
        with mock.patch.object(apertura, "rehacer", side_effect=ValueError("ruta/secreta")):
            app.arreglar(self.carpeta, "es")
        self.assertNotIn("ruta/secreta", app.estado_apertura(self.carpeta)["mensaje"])
        self.assertIn("ruta/secreta", (self.carpeta / "error.txt").read_text(encoding="utf-8"))

    def test_el_panel_puede_ver_el_antes_y_los_cuadros_pero_nada_mas(self):
        from retina.demo import PERMITIDO
        self.assertTrue(PERMITIDO.match("/casos/abcdef123456/apertura-antes.jpg"))
        self.assertTrue(PERMITIDO.match("/casos/abcdef123456/apertura-cuadro1-ilustracion-ia.png"))
        self.assertFalse(PERMITIDO.match("/casos/abcdef123456/apertura.json"))
        self.assertFalse(PERMITIDO.match("/casos/abcdef123456/video.mp4"))


if __name__ == "__main__":
    unittest.main()
