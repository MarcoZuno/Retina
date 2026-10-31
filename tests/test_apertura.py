"""La apertura arreglada: reglas de texto, comprobación con SAM, correcciones y lo que nunca llega a la persona.

Sin API, sin llaves y sin red: el modelo, Muse Image y SAM son funciones falsas.
Corren con:  python -m unittest discover -s tests   (desde la raíz del repo)
"""
from __future__ import annotations

import importlib.util
import json
import os
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
        self.assertIn("formato", ids(["no es un objeto"]))
        self.assertIn("formato", ids(None))

    def test_un_millon_que_no_viene_del_video_se_rechaza(self):
        self.assertIn("cifras", ids(buena(voz=VOZ.replace("2 horas", "un millón de horas"))))
        self.assertIn("cifras", ids(buena(voz=VOZ.replace("2 horas", "trece horas"))))

    def test_un_nombre_en_un_cuadro_que_no_viene_del_video_se_rechaza(self):
        self.assertIn("nombres", ids(buena(cuadros=[CUADROS[0], "Un auto Tesla junto a la mesa.", CUADROS[2]])))

    def test_un_gentilicio_en_un_cuadro_no_es_un_nombre(self):
        self.assertNotIn("nombres", ids(buena(cuadros=[CUADROS[0], "A baker in a Mexican kitchen.", CUADROS[2]])))

    def test_un_gentilicio_en_la_voz_si_tiene_que_venir_del_video(self):
        self.assertIn("nombres", ids(buena(voz=VOZ + " Lo cuenta un panadero Mexican.")))

    def test_un_cuadro_sin_punto_no_vuelve_nombre_el_inicio_del_siguiente(self):
        self.assertNotIn("nombres", ids(buena(cuadros=["Una pieza de pan dulce", "Bolsa de tela sobre la mesa", "Canasta con pan fresco"])))

    def test_las_cifras_con_letra_que_faltaban_tambien_cuentan(self):
        for palabra in ("thirteen", "eleven", "nineteen", "docena", "dozen", "catorce"):
            self.assertIn("cifras", ids(buena(voz=VOZ.replace("2 horas", f"{palabra} horas"))), palabra)

    def test_un_titulo_en_otro_idioma_no_obliga_a_usar_sus_palabras(self):
        datos = {**DATOS, "tema_obligatorio": False}
        self.assertNotIn("tema", ids(buena(voz="Esto casi nadie lo hace bien. " + VOZ), datos))


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

        def dibujar(i, cuadro):
            self.dibujos.append(i)
            return Path(f"apertura-cuadro{i}-ilustracion-ia.png")

        self.datos_que_recibio = []

        def pedir_y_anotar(datos, aviso):
            self.datos_que_recibio.append(datos)
            return pedir(datos, aviso)

        self.medir = mock.Mock(side_effect=lambda imagen, c: next(medidas))
        return apertura.lazo(DATOS, concepto, pedir_y_anotar, dibujar, self.medir)

    SE_VE = {"concepto": "bread", "aparece": True, "primer_segundo": 0.0}
    NO_SE_VE = {"concepto": "bread", "aparece": False, "primer_segundo": None}

    def test_pasa_a_la_primera_y_dibuja_los_tres_cuadros(self):
        r = self.correr([buena()], [self.SE_VE])
        self.assertTrue(r["aprobada"])
        self.assertEqual(r["vueltas"], 0)
        self.assertEqual(self.dibujos, [1, 2, 3])
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
        self.assertEqual(self.dibujos, [1, 2, 3])
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
        self.assertNotIn("objeto_prometido", self.datos_que_recibio[0])
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

    def test_quien_escribe_recibe_el_objeto_prometido(self):
        self.correr([buena()], [self.SE_VE])
        self.assertEqual(self.datos_que_recibio[0]["objeto_prometido"], "bread")

    def test_si_muse_image_falla_gasta_un_intento_y_sigue(self):
        fallas = iter([RuntimeError("rechazó el dibujo")])

        def dibujar(i, cuadro):
            for e in fallas:
                raise e
            return Path(f"apertura-cuadro{i}-ilustracion-ia.png")

        r = apertura.lazo(DATOS, None, lambda d, a: buena(), dibujar, mock.Mock())
        self.assertTrue(r["aprobada"])
        self.assertEqual((r["vueltas"], r["intentos"][0]["problemas"][0]["id"]), (1, "cuadros"))

    def test_si_un_cuadro_no_se_puede_dibujar_nunca_no_sale_nada(self):
        def dibujar(i, cuadro):
            if i == 3:
                raise OSError("sin red")
            return Path(f"apertura-cuadro{i}-ilustracion-ia.png")

        r = apertura.lazo(DATOS, None, lambda d, a: buena(), dibujar, mock.Mock())
        self.assertFalse(r["aprobada"])
        self.assertIsNone(r["despues"])

    def test_el_tope_de_gasto_detiene_todo(self):
        with self.assertRaises(meta_api.TopeAlcanzado):
            self.correr([meta_api.TopeAlcanzado("tope")])


class PedirASparkOpen(unittest.TestCase):
    def setUp(self):  # que vaya por Baseten no depende de que la PC tenga una llave real en su .env
        env = mock.patch.dict(os.environ, {"BASETEN_API_KEY": "llave-de-prueba", "RETINA_ENV": str(Path(__file__).parent / "no-hay.env")})
        env.start()
        self.addCleanup(env.stop)

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
        self.assertIn("9 días", datos["fuente"])
        self.assertIn("5 pasos", datos["fuente"])
        self.assertIn("Y dura 9 días.", datos["resto_de_lo_que_se_dice"])
        self.assertNotIn("nivel_de_riesgo", datos)

    def test_un_titulo_en_otro_idioma_que_el_video_apaga_la_regla_del_tema(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t); self.preparar(d)
            self.assertFalse(apertura.datos_de_apertura(d, "How to keep the bread from going stale at home", "es")["tema_obligatorio"])
            self.assertTrue(apertura.datos_de_apertura(d, TITULO, "es")["tema_obligatorio"])

    def test_un_turno_sin_texto_no_truena_el_antes(self):
        with tempfile.TemporaryDirectory() as t:
            antes = apertura.antes_del_cambio(Path(t), {"frases": [{"segundo": 1.0, "dice": None}, {"segundo": 2.0, "dice": "Hola"}]})
        self.assertEqual(antes["voz"], "Hola")

    def test_si_algo_truena_a_media_corrida_no_queda_ningun_dibujo_sin_aprobar(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(apertura, "lazo", side_effect=OSError("sin red")):
            d = Path(t); self.preparar(d)
            suelto = d / "apertura-cuadro1-ilustracion-ia.png"
            suelto.write_bytes(b"x")
            with self.assertRaises(OSError):
                apertura.armar(d, TITULO, "bread")
            self.assertFalse(suelto.exists())

    def test_una_apertura_ya_hecha_vuelve_a_quedar_en_el_resultado(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t); self.preparar(d)
            (d / "apertura.json").write_text(json.dumps({"aprobada": True}), encoding="utf-8")
            apertura.rehacer(d)
            self.assertEqual(json.loads((d / "resultado.json").read_text(encoding="utf-8"))["apertura"], {"aprobada": True})

    def test_el_idioma_sale_del_video_y_no_del_panel(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t); self.preparar(d)
            self.assertEqual(apertura.datos_de_apertura(d, TITULO, "en")["idioma_de_la_apertura"], "español")

    def test_queda_anotada_en_el_resultado_con_el_titulo_intacto(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(apertura.sam, "objeto_del_titulo", return_value=None), \
                mock.patch.object(apertura, "pedir", return_value=buena(voz=VOZ.replace("2 horas", "5 pasos"))), \
                mock.patch.object(apertura, "dibujar_cuadro",
                                  side_effect=lambda c, i, texto: c / f"apertura-cuadro{i}-ilustracion-ia.png"):
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

    def test_una_apertura_que_no_paso_se_puede_volver_a_intentar(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(apertura.sam, "objeto_del_titulo", return_value=None),                 mock.patch.object(apertura, "pedir", return_value=buena(voz=VOZ.replace("2 horas", "5 pasos"))),                 mock.patch.object(apertura, "dibujar_cuadro",
                                  side_effect=lambda c, i, texto: c / f"apertura-cuadro{i}-ilustracion-ia.png"):
            d = Path(t); self.preparar(d)
            (d / "apertura.json").write_text(json.dumps({"aprobada": False}), encoding="utf-8")
            self.assertTrue(apertura.rehacer(d)["aprobada"])

    def test_un_video_en_otro_alfabeto_no_gasta_y_lo_dice(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(apertura, "lazo", side_effect=AssertionError("gastó")):
            d = Path(t); self.preparar(d)
            (d / "transcribir.json").write_text(json.dumps({"arranque_voz_ms": 0, "silencios": [], "turnos": [{"startMs": 0, "transcript": "这是一个关于面包的视频，我们今天来学习怎么保存面包。" * 3}]}), encoding="utf-8")
            s = apertura.armar(d, "如何保存面包", None)
        self.assertFalse(s["aprobada"])
        self.assertTrue(s["otro_alfabeto"])

    def test_no_se_paga_dos_veces_por_la_misma_revision(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(apertura, "pedir", side_effect=AssertionError("pagó")):
            d = Path(t); self.preparar(d)
            (d / "apertura.json").write_text(json.dumps({"aprobada": True}), encoding="utf-8")
            self.assertEqual(apertura.rehacer(d), {"aprobada": True})

    def test_el_dibujo_sale_solo_de_lo_que_se_escribio(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(storyboard, "dibujar_uno") as dibujar:
            apertura.dibujar_cuadro(Path(t), 1, "Una mesa de cocina.")
        self.assertTrue(dibujar.call_args.args[0].endswith("Una mesa de cocina."))


class VocabularioDeSam(unittest.TestCase):
    VOCABULARIO = {"tortilla": "food", "dog": "dog"}

    def setUp(self):
        parche = mock.patch.object(apertura.sam, "_vocabulario", return_value=self.VOCABULARIO)
        parche.start()
        self.addCleanup(parche.stop)

    def test_lo_que_no_se_puede_comprobar_no_se_le_ofrece_a_spark(self):
        respuesta = {"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"objeto": "dog"})}]}]}
        with mock.patch.object(meta_api, "responder", return_value=respuesta) as responder:
            self.assertEqual(apertura.sam.objeto_del_titulo("Un perro en la calle"), "dog")
        cuerpo = responder.call_args.args[1]
        opciones = cuerpo["text"]["format"]["schema"]["properties"]["objeto"]["enum"]
        self.assertEqual(sorted(opciones), ["dog", "ninguno", "tortilla"])

    def test_se_escribe_la_palabra_prometida_y_se_busca_la_que_sam_reconoce(self):
        with tempfile.TemporaryDirectory() as t, \
                mock.patch.object(apertura, "pedir", return_value=buena(voz=VOZ.replace("2 horas", "5 pasos"))) as pedir, \
                mock.patch.object(apertura, "dibujar_cuadro",
                                  side_effect=lambda c, i, texto: c / f"apertura-cuadro{i}-ilustracion-ia.png"), \
                mock.patch.object(apertura.sam, "medir_imagen",
                                  return_value={"concepto": "food", "aparece": True, "primer_segundo": 0.0}) as medir:
            d = Path(t); Rehacer().preparar(d)
            s = apertura.armar(d, TITULO, "tortilla")
        self.assertEqual(pedir.call_args.args[0]["objeto_prometido"], "tortilla")
        self.assertEqual(medir.call_args.args[1], "food")
        self.assertEqual(s["objeto"], "tortilla")
        self.assertEqual({c["id"]: c.get("objeto") for c in s["comprobaciones"]}["promesa"], "food")

    def test_la_revision_del_borrador_recuerda_lo_que_prometia_el_titulo(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(apertura.sam, "objeto_del_titulo", return_value="tortilla"), \
                mock.patch.object(apertura.sam, "medir",
                                  return_value={"concepto": "food", "aparece": False, "primer_segundo": None}) as medir:
            d = Path(t)
            apertura.sam.medir_promesa(d, "Las tortillas de hoy")
            medir.assert_called_once_with(d, "food")
            self.assertEqual(apertura.prometido(d, "Las tortillas de hoy"), "tortilla")


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


class Medicion(unittest.TestCase):
    def test_la_trampa_solo_pasa_con_sus_10_cuadros(self):
        spec = importlib.util.spec_from_file_location("apertura_casos", RAIZ / "eval" / "apertura_casos.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        self.assertTrue(modulo.trampa_pasa([{"rechazo": True}] * 9 + [{"rechazo": False}]))
        self.assertFalse(modulo.trampa_pasa([{"rechazo": True}] * 9))
        self.assertFalse(modulo.trampa_pasa([{"rechazo": True}] * 8 + [{"rechazo": False}] * 2))


class MedicionNueva(unittest.TestCase):
    def modulo(self, nombre):
        sys.path.insert(0, str(RAIZ / "eval"))
        spec = importlib.util.spec_from_file_location(nombre, RAIZ / "eval" / f"{nombre}.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_la_trampa_lejana_no_usa_palabras_generales_ni_de_la_misma_familia(self):
        m = self.modulo("apertura_v2")
        self.assertEqual(m.lejano("dog", ["cat", "food", "bread"], 0), "food")
        self.assertIsNone(m.lejano("dog", ["cat", "rabbit"], 0))

    def test_la_trampa_cercana_es_otro_objeto_de_la_familia(self):
        m = self.modulo("apertura_v2")
        self.assertEqual(m.cercano("dog"), "cat")
        self.assertIsNone(m.cercano("trophy"))

    def test_el_juez_solo_cuenta_lo_que_elige_en_los_dos_ordenes(self):
        m = self.modulo("juez_aperturas")
        filas = [{"fiel": True, "queda_algo": True, "NR": "nueva", "RN": "nueva"}] * 15 + [{"fiel": True, "queda_algo": True, "NR": "real", "RN": "real"}] * 5
        filas += [{"fiel": False, "queda_algo": False, "NR": "real", "RN": "nueva"}] * 5
        r = m.resumir(filas, False)
        self.assertEqual((r["firmes"], r["gana_nueva"], r["pct_nueva"], r["cambia_con_el_orden"]), (20, 15, 75, 5))
        self.assertTrue(r["pasa_par"])
        self.assertEqual((r["fieles"], r["pasa_fieles"]), (20, True))

    def test_el_juez_no_pasa_con_pocos_pares_decididos(self):
        m = self.modulo("juez_aperturas")
        r = m.resumir([{"fiel": True, "queda_algo": True, "NR": "nueva", "RN": "nueva"}] * 19, False)
        self.assertFalse(r["pasa_par"])

    def test_el_arranque_real_del_juez_se_mide_como_en_el_panel(self):
        m = self.modulo("juez_aperturas")
        todo, real = m.del_video([[0, "hola"], [14, "que tal"], [16, "adios"], [20, None]])
        self.assertEqual((todo, real), ("hola que tal adios", "hola que tal"))


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
        (self.carpeta / "apertura.json").write_text(json.dumps({"aprobada": True}), encoding="utf-8")
        self.assertEqual(app.pedir_apertura(self.carpeta, self.fila, "es"), (200, {"estado": "listo"}))
        self.fila.submit.assert_not_called()

    def test_la_que_no_paso_se_puede_volver_a_pedir(self):
        (self.carpeta / "apertura.json").write_text(json.dumps({"aprobada": False}), encoding="utf-8")
        self.assertEqual(app.pedir_apertura(self.carpeta, self.fila, "es")[0], 202)
        self.fila.submit.assert_called_once()

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
