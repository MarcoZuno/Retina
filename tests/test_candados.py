"""Candados que una auditoría encontró flojos (29-oct): tarjeta sin validar, citas que proponen, inglés,
cifras con letra, SAM sin personas, tope de gasto en paralelo, límites del agente y sí/no de la ficha.

Sin API, sin llaves y sin red: modelos falsos y un registro de costos en una carpeta temporal.
Corren con:  python -m unittest discover -s tests   (desde la raíz del repo)
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import subprocess
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

from retina import agente, baseten, explicar, integridad, meta_api, sam  # noqa: E402
from retina.ficha import valida  # noqa: E402
from test_ficha import BUENA  # noqa: E402
from test_reglas import DATOS, tarjeta  # noqa: E402


# 1. Nada que no pasó el validador sale en la tarjeta ------------------------------------------------------------

class TarjetaSinValidar(unittest.TestCase):
    def test_si_el_validador_rechaza_dos_veces_no_sale_ningun_texto_del_modelo(self):
        mala = tarjeta(por_que="Comenta SÍ abajo y comparte con un amigo.", lo_que_funciona="Pide que comenten abajo.",
                       lo_bueno=["Pide que se suscriban y funciona."], lo_flojo=["Etiqueta a un amigo."],
                       que_cambiar="Di «comenta SÍ» al inicio", pasos=["Pide comentarios"],
                       mejoras_opcionales=["Sortea un celular."], storyboard=["Cuadro: link en la bio"],
                       anzuelo_detectado="pide_interaccion", anzuelo_frase="Comenta SÍ", anzuelo_momento_s=3.0,
                       no_pude_verificar=["Comenta abajo"], momento_s=2.0, confianza="alta")
        intentos = [{"motor": "api", "sugerencia": mala["que_cambiar"], "problemas": ["bloqueada"]}] * 2
        with tempfile.TemporaryDirectory() as d, mock.patch.object(explicar, "datos_del_arranque", return_value=DATOS), \
                mock.patch.object(explicar, "escribir", return_value=(mala, intentos, "api")):
            s = explicar.explicar(Path(d), {}, "api")
            guardada = json.loads((Path(d) / "explicar.json").read_text(encoding="utf-8"))
        for tarj in (s, guardada):
            texto = json.dumps({k: v for k, v in tarj.items() if k not in ("licencia", "no_pude_verificar")}, ensure_ascii=False)
            self.assertNotRegex(texto.lower(), r"coment|compart|suscrib|etiquet|sortea|la bio")
            for campo in ("por_que", "lo_que_funciona", "que_cambiar", "anzuelo_frase"):
                self.assertEqual(tarj[campo], "", campo)
            for campo in ("lo_bueno", "lo_flojo", "pasos", "mejoras_opcionales", "storyboard"):
                self.assertEqual(tarj[campo], [], campo)
            self.assertEqual((tarj["tipo_de_cambio"], tarj["anzuelo_detectado"]), ("ninguno", "ninguno"))
            self.assertEqual(len(tarj["no_pude_verificar"]), 1)  # solo el aviso de Retina, no lo que escribió el modelo
            self.assertNotIn("Comenta", tarj["no_pude_verificar"][0])
            self.assertEqual(set(tarj) - {"licencia"}, set(explicar.esquema()["required"]))

    def test_una_tarjeta_vacia_es_valida_para_el_panel_pero_no_pasa_el_validador_en_alto(self):
        vacia = explicar.tarjeta_sin_validar()
        self.assertEqual(vacia["lo_bueno"], [])
        self.assertTrue(explicar.revisar(vacia, DATOS))  # nunca se confunde con una tarjeta que pasó


# 2. Lo que se propone poner entre comillas se revisa ------------------------------------------------------------

class CitasQueProponen(unittest.TestCase):
    def bloqueada(self, que, pasos=None):
        p = explicar.revisar(tarjeta(que_cambiar=que, pasos=pasos or ["Haz el cambio en el editor."]), DATOS)
        return any("(frases:" in x for x in p)  # lo bloqueó el filtro de anzuelos

    def test_lo_que_se_propone_decir_se_revisa_igual(self):
        for texto in ["Reemplaza el saludo por «Comenta SÍ abajo»", "Sustituye el saludo con “Comenta SÍ abajo”",
                      "Cambia el saludo por «Comenta SÍ abajo»", "Quita el saludo y pon «Comenta SÍ abajo»",
                      "Corta el saludo y escribe en pantalla «Etiqueta a un amigo»",
                      "Replace the greeting with “Comment YES below”", "Cut the intro and say «Tag a friend»",
                      "Remove the intro and write \"Link in bio\" on screen", "Reemplaza «Hola» por «Dale like»"]:
            with self.subTest(texto=texto):
                self.assertTrue(self.bloqueada(texto), texto)
                self.assertTrue(self.bloqueada("Mueve el plano de la pila al segundo 0.", [texto]), texto)

    def test_citar_lo_que_ya_dice_el_video_para_quitarlo_sigue_pasando(self):
        datos = {**DATOS, "frases": [{"segundo": 4.9, "dice": "Comparte esta información con tu familia."}]}
        for que in ["Quita «Comparte esta información con tu familia» del segundo 4.9",
                    "Reemplaza «Comparte esta información con tu familia» por un corte directo al dato",
                    "Remove “Comparte esta información con tu familia” from second 4.9"]:
            with self.subTest(que=que):
                self.assertEqual(explicar.revisar(tarjeta(que_cambiar=que), datos), [])


# 3. Reglas en inglés ---------------------------------------------------------------------------------------------

class ReglasEnIngles(unittest.TestCase):
    def test_anzuelos_en_ingles(self):
        for texto in ["Ask viewers to comment YES below", "tag a friend", "link in bio", "Share this with your family",
                      "Subscribe for more", "Watch until the end", "You won't believe what happened next",
                      "This shocking clip", "A natural cure for everything", "Win a phone in our giveaway",
                      "Repost the clip from another account", "Join the WhatsApp group", "Hit the like button",
                      "Drop a comment", "Follow me", "Send it to your friends", "Leave a comment", "Double tap"]:
            with self.subTest(texto=texto):
                self.assertTrue(integridad.revisar(texto), f"debió bloquear: {texto}")

    def test_cada_categoria_tiene_su_equivalente_en_ingles(self):
        con_ingles = {"pide_interaccion": "comment", "mira_hasta_el_final": "until the end", "esconde_el_dato": "what happened next",
                      "exageracion": "unbelievable", "cura_milagrosa": "miracle", "material_ajeno": "repost",
                      "sorteo_falso": "giveaway", "saca_de_la_plataforma": "link in bio", "ia_sin_etiqueta": "no ai label"}
        ids_ = {a["id"] for a in integridad.reglas()["anzuelos"]}
        self.assertEqual(ids_, set(con_ingles))
        for id_, texto in con_ingles.items():
            with self.subTest(id=id_):
                self.assertIn(id_, [r["id"] for r in integridad.revisar(texto)])

    def test_intocables_en_ingles(self):
        for texto in ["Remove the page logo", "Cut the health warning", "Delete the title", "Blur is not needed: remove the blur",
                      "Hide the credits", "Take out the disclaimer", "Remove the pixelation", "Cut the legal notice",
                      "Get rid of the channel logo", "Move the headline", "Drop the closing question"]:
            with self.subTest(texto=texto):
                self.assertTrue(explicar.toca_intocable(texto), f"debió tocar un intocable: {texto}")

    def test_sugerencias_normales_en_ingles_pasan(self):
        for texto in ["Put the key fact on screen at second 3", "Move the product shot to second 0",
                      "Cut the silence from second 3 to 8", "Show the tortilla stack in the first frame"]:
            with self.subTest(texto=texto):
                self.assertEqual(integridad.revisar(texto), [])
                self.assertEqual(explicar.toca_intocable(texto), [])

    def test_la_tarjeta_en_ingles_se_bloquea_en_el_validador(self):
        p = explicar.revisar(tarjeta(que_cambiar="Ask viewers to comment YES below", pasos=["Add the text at second 1."]), DATOS)
        self.assertTrue(p)
        p = explicar.revisar(tarjeta(que_cambiar="Remove the page logo", pasos=["Cut it at second 1."]), DATOS)
        self.assertTrue(any("intocable" in x for x in p), p)


# 4. Cifras escritas con letra ------------------------------------------------------------------------------------

class CifrasConLetra(unittest.TestCase):
    def test_porcentajes_con_letra_en_espanol_e_ingles(self):
        for texto in ["En el segundo 4.9 se va doce por ciento de la gente.", "Se va el cien por ciento.",
                      "Se queda el treinta y cinco porciento.", "About twelve percent leave at second 4.9.",
                      "Twenty-five per cent stay.", "De cada cien se van doce.", "Out of 100 viewers, twelve leave.",
                      "Out of every hundred, a few leave.", "Se van tres de cada diez.", "uno de cada cien"]:
            for campo, valor in (("por_que", texto), ("lo_bueno", [texto]), ("pasos", [texto])):
                with self.subTest(texto=texto, campo=campo):
                    p = explicar.revisar(tarjeta(**{campo: valor}), DATOS)
                    self.assertTrue(any("jerga" in x or "trae jerga" in x for x in p), p)

    def test_texto_normal_con_numeros_en_palabras_pasa(self):
        for texto in ["En el segundo 4.9 se ve la pila de tortillas.", "Deja tres segundos de silencio antes del dato.",
                      "Por cada plano, un texto corto.", "Cuts every two seconds feel fast."]:
            with self.subTest(texto=texto):
                self.assertEqual([x for x in explicar.revisar(tarjeta(por_que=texto), DATOS) if "jerga" in x], [])


# 5. Sin nombres de marcas internas en las reglas -----------------------------------------------------------------

class SinMarcasInternas(unittest.TestCase):
    def test_las_reglas_no_nombran_marcas_de_la_empresa(self):
        marca = "FE" + "PA"
        for archivo in (RAIZ / "reglas").glob("*.json"):
            texto = archivo.read_text(encoding="utf-8")
            with self.subTest(archivo=archivo.name):
                self.assertNotIn(marca.lower(), texto.lower())
                self.assertNotIn("badabun", texto.lower())


# 6. SAM: lista cerrada, nunca personas ---------------------------------------------------------------------------

PERSONAS = ["guard in car", "infant in bed", "bride on stage", "fans in stadium", "guardia en la calle", "bebé", "baby", "novia",
            "fan", "fans", "crowd", "público", "man", "woman", "kid", "niño", "worker", "police", "man in street",
            "crowd in stadium", "baby dog", "dog and man", "police car", "worker in factory", "security guard", "mujer",
            "red dress", "hands holding bread", "face", "b a b y", "bаby"]  # la última lleva una «а» cirílica


class SamListaCerrada(unittest.TestCase):
    def test_ninguna_palabra_de_persona_pasa_por_ningun_camino(self):
        for c in PERSONAS:
            with self.subTest(concepto=c):
                self.assertIsNotNone(sam.rechazo(c))
                self.assertTrue(sam.es_persona(c))

    def test_solo_lo_de_la_lista_pasa(self):
        for c in ["flooded street", "stack of tortillas", "sweet bread", "dog", "landslides", "dog in car",
                  "burning building", "plate of food", "Fire in forest"]:
            with self.subTest(concepto=c):
                self.assertIsNone(sam.rechazo(c))
        for c in ["unicorn", "spaceship", "dog flying", "", "   ", "123", "!!!", "dog unicorn"]:
            with self.subTest(concepto=c):
                self.assertIsNotNone(sam.rechazo(c))
        self.assertIsNotNone(sam.rechazo(None))

    def test_las_tres_listas_no_se_cruzan(self):
        d = json.loads(sam.PERMITIDOS.read_text(encoding="utf-8"))
        permitidas, modificadores, personas = set(d["palabras"]), set(d["modificadores"]), set(d["personas"])
        self.assertEqual(permitidas & personas, set())
        self.assertEqual(modificadores & personas, set())
        self.assertEqual(modificadores & permitidas, set())

    def test_la_herramienta_del_agente_la_linea_de_comandos_y_la_funcion_publica_rechazan_antes_de_gastar(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(meta_api, "reservar", side_effect=AssertionError("llamó a la API")), \
                mock.patch.object(meta_api, "subir_archivo", side_effect=AssertionError("subió el video")):
            carpeta = Path(d)
            for c in ("guard in car", "infant in bed", "bride on stage", "fans in stadium"):
                with self.subTest(concepto=c):
                    self.assertIn("error", sam.medir(carpeta, c))  # función pública
                    caja = object.__new__(agente.Caja)
                    caja.carpeta, caja.datos, caja.vistos = carpeta, DATOS, []
                    self.assertIn("error", caja.correr("medir_lo_prometido", {"concepto": c}))  # herramienta del agente
                    with mock.patch.object(sys, "argv", ["sam", d, "--concepto", c]), contextlib.redirect_stdout(io.StringIO()) as salida:
                        sam.main()  # línea de comandos
                    self.assertIn("error", json.loads(salida.getvalue()))
                    with self.assertRaises(ValueError):  # última puerta, aunque alguien llame directo al segmentador
                        asyncio.run(sam._segmentar("file-1", c))
            self.assertFalse(list(carpeta.iterdir()))  # ni siquiera se recortó el clip


# 7. Tope de gasto en paralelo -----------------------------------------------------------------------------------------

class ConRegistro(unittest.TestCase):
    """Un registro de costos propio, sin .env ni llaves reales."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.costos = Path(self.tmp.name) / "costos.jsonl"
        env = mock.patch.dict(os.environ, {"RETINA_COSTOS": str(self.costos), "RETINA_ENV": str(Path(self.tmp.name) / "no-hay.env"),
                                           "MODEL_API_KEY": "prueba", "BASETEN_API_KEY": "prueba", "RETINA_TOPE_USD": "50"})
        env.start()
        self.addCleanup(env.stop)

    def filas(self) -> list[dict]:
        return [json.loads(l) for l in self.costos.read_text(encoding="utf-8").splitlines() if l.strip()] if self.costos.exists() else []


TOKENS_20_USD = 4_705_882  # a 4.25 USD por millón de tokens de salida: casi exactamente 20 USD


class RespuestaFalsa:
    status_code = 200

    def __init__(self, tokens=TOKENS_20_USD):
        self.tokens = tokens

    def json(self):
        return {"usage": {"input_tokens": 0, "output_tokens": self.tokens}, "output": []}


def pedir_lento(*_a, **_k):
    time.sleep(0.05)  # que las llamadas se traslapen
    return RespuestaFalsa()


def llamar_spark() -> bool:
    try:
        meta_api.responder("prueba", {"model": "muse-spark-1.3", "max_output_tokens": TOKENS_20_USD})
        return True
    except meta_api.TopeAlcanzado:
        return False


class TopeEnParalelo(ConRegistro):
    def test_ocho_hilos_a_la_vez_solo_pasan_los_que_caben(self):
        with mock.patch.object(meta_api, "_pedir", pedir_lento), ThreadPoolExecutor(8) as ex:
            pasaron = list(ex.map(lambda _: llamar_spark(), range(8)))
        self.assertEqual(sum(pasaron), 2, pasaron)  # 20 + 20 = 40 de 50; la tercera ya no cabe
        self.assertLessEqual(meta_api.gastado_usd(), 50)
        self.assertEqual(len(self.filas()), 2)
        self.assertEqual(meta_api.reservado_usd(), 0)  # nada se queda apartado

    def test_dos_procesos_a_la_vez_tampoco_se_pasan(self):
        codigo = (
            "import sys, time\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from unittest import mock\n"
            "from retina import meta_api\n"
            "class R:\n"
            "    status_code = 200\n"
            "    def json(self):\n"
            f"        return {{'usage': {{'input_tokens': 0, 'output_tokens': {TOKENS_20_USD}}}, 'output': []}}\n"
            "def falsa(*a, **k):\n"
            "    time.sleep(0.05)\n"
            "    return R()\n"
            "ok = 0\n"
            "with mock.patch.object(meta_api, '_pedir', falsa):\n"
            "    for _ in range(4):\n"
            f"        try:\n"
            f"            meta_api.responder('x', {{'model': 'muse-spark-1.3', 'max_output_tokens': {TOKENS_20_USD}}})\n"
            "            ok += 1\n"
            "        except meta_api.TopeAlcanzado:\n"
            "            pass\n"
            "print(ok)\n"
        )
        procesos = [subprocess.Popen([sys.executable, "-c", codigo, str(RAIZ / "src")], stdout=subprocess.PIPE, text=True)
                    for _ in range(2)]
        total = sum(int(p.communicate(timeout=120)[0].strip()) for p in procesos)
        self.assertEqual(total, 2)
        self.assertEqual(len(self.filas()), 2)

    def test_una_llamada_que_falla_con_error_http_suelta_lo_apartado(self):
        malo = mock.Mock(status_code=500, **{"json.return_value": {"error": {"message": "x"}}})
        with mock.patch.object(meta_api, "_pedir", return_value=malo), self.assertRaises(RuntimeError):
            meta_api.responder("prueba", {"model": "muse-spark-1.3", "max_output_tokens": TOKENS_20_USD})
        self.assertEqual(meta_api.reservado_usd(), 0)

    def test_si_no_sabemos_si_cobro_el_peor_caso_se_queda_apartado(self):
        with mock.patch.object(meta_api, "_pedir", side_effect=ConnectionError("sin red")), self.assertRaises(ConnectionError):
            meta_api.responder("prueba", {"model": "muse-spark-1.3", "max_output_tokens": TOKENS_20_USD})
        self.assertAlmostEqual(meta_api.reservado_usd(), 20, delta=0.01)
        with mock.patch.object(meta_api, "_pedir", pedir_lento):
            self.assertFalse(llamar_spark() and llamar_spark() and llamar_spark())  # y cuenta contra el tope

    def test_el_costo_real_reemplaza_a_la_reserva(self):
        with mock.patch.object(meta_api, "_pedir", return_value=RespuestaFalsa(1000)):
            meta_api.responder("prueba", {"model": "muse-spark-1.3", "max_output_tokens": TOKENS_20_USD})
        self.assertAlmostEqual(meta_api.gastado_usd(), 1000 * 4.25 / 1e6, places=6)
        self.assertEqual(meta_api.reservado_usd(), 0)

    def test_un_estimado_que_no_es_numero_no_llama(self):
        for malo in (float("nan"), float("inf"), -1.0, "10"):
            with self.subTest(estimado=malo), self.assertRaises(meta_api.TopeAlcanzado):
                meta_api.reservar("prueba", malo)

    def test_una_reserva_huerfana_vence_al_dia_siguiente(self):
        id_ = meta_api.reservar("prueba", 30)
        self.assertEqual(meta_api.reservado_usd(), 30)
        with meta_api._candado():
            r = meta_api._leer_reservas()
            r[id_]["t"] -= meta_api.RESERVA_VIGENCIA_S + 1
            meta_api._guardar_reservas(r)
        self.assertEqual(meta_api.reservado_usd(), 0)


class TopeEscrito(ConRegistro):
    def tope(self, valor):
        with mock.patch.dict(os.environ, {"RETINA_TOPE_USD": valor}):
            return meta_api.tope_usd()

    def test_un_tope_que_no_es_un_numero_sano_se_ignora(self):
        for malo in ("nan", "NaN", "inf", "-inf", "-5", "abc", "", "  ", "1e999", "cincuenta"):
            with self.subTest(tope=malo):
                self.assertEqual(self.tope(malo), meta_api.TOPE_POR_OMISION_USD)
        self.assertLessEqual(meta_api.TOPE_POR_OMISION_USD, meta_api.TOPE_MAXIMO_USD)

    def test_un_tope_sano_se_respeta_y_el_techo_duro_manda(self):
        self.assertEqual(self.tope("10"), 10)
        self.assertEqual(self.tope("0"), 0)
        self.assertEqual(self.tope("1000"), meta_api.TOPE_MAXIMO_USD)

    def test_con_tope_nan_no_se_pasa_del_tope_por_omision(self):
        with mock.patch.dict(os.environ, {"RETINA_TOPE_USD": "nan"}), mock.patch.object(meta_api, "_pedir", pedir_lento):
            self.assertTrue(llamar_spark())
            self.assertTrue(llamar_spark())
            self.assertFalse(llamar_spark())


class FalsoOpenAI:
    """Un cliente falso de Baseten: cada llamada gasta todos los tokens que se le permitieron."""

    def __init__(self, **_):
        self.chat = self.completions = self

    def create(self, **kw):
        time.sleep(0.05)
        uso = mock.Mock(prompt_tokens=0, completion_tokens=kw["max_tokens"], prompt_tokens_details=None)
        return mock.Mock(usage=uso, choices=[mock.Mock(message=mock.Mock(content="{}", tool_calls=None))])


def llamar_baseten(max_tokens: int) -> bool:
    try:
        baseten.completar("prueba", [{"role": "user", "content": "hola"}], max_tokens)
        return True
    except meta_api.TopeAlcanzado:
        return False


class TopeDeBaseten(ConRegistro):
    def setUp(self):
        super().setUp()
        m = mock.patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=FalsoOpenAI)})
        m.start()
        self.addCleanup(m.stop)

    def test_baseten_respeta_el_tope_que_pone_el_usuario(self):
        self.costos.write_text(json.dumps({"servicio": "describir", "usd": 0.9}) + "\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"RETINA_TOPE_USD": "1"}):
            self.assertFalse(llamar_baseten(1_000_000))  # peor caso 4.25 USD: pasa de 1
            self.assertTrue(llamar_baseten(1000))
        self.assertEqual(len(self.filas()), 2)  # solo la que cupo se anotó

    def test_baseten_respeta_su_propio_tope(self):
        self.costos.write_text(json.dumps({"servicio": "baseten-explicar", "usd": baseten.TOPE_BASETEN_USD - 0.01}) + "\n",
                               encoding="utf-8")
        with mock.patch.dict(os.environ, {"RETINA_TOPE_USD": str(meta_api.TOPE_MAXIMO_USD)}):  # el tope general no estorba
            self.assertFalse(llamar_baseten(8000))  # 0.034 USD de peor caso no caben en 0.01
            self.assertTrue(llamar_baseten(1000))

    def test_baseten_en_paralelo_no_se_pasa(self):
        with mock.patch.dict(os.environ, {"RETINA_TOPE_USD": "1"}), ThreadPoolExecutor(8) as ex:
            pasaron = list(ex.map(lambda _: llamar_baseten(60_000), range(8)))  # 0.255 USD cada una
        self.assertEqual(sum(pasaron), 3, pasaron)
        self.assertLessEqual(baseten.gastado_usd(), 1)

    def test_una_llamada_de_baseten_pagada_queda_anotada_y_sin_reserva(self):
        self.assertTrue(llamar_baseten(2000))
        fila = self.filas()[0]
        self.assertEqual((fila["servicio"], fila["salida"]), ("baseten-prueba", 2000))
        self.assertEqual(meta_api.reservado_usd(), 0)


class LlamadaPagadaSiempreQuedaAnotada(ConRegistro):
    def test_sam_anota_el_gasto_aunque_falle_a_media_corrida(self):
        async def falla(*_):
            raise RuntimeError("se cayó SAM")
        with tempfile.TemporaryDirectory() as d, mock.patch.object(sam, "recortar", return_value=Path(d) / "clip.mp4"), \
                mock.patch.object(meta_api, "subir_archivo", return_value="file-1"), \
                mock.patch.object(meta_api, "borrar_archivo"), mock.patch.object(sam, "_segmentar", falla):
            with self.assertRaises(RuntimeError):
                sam.medir(Path(d), "flooded street")
        fila = self.filas()[0]
        self.assertEqual(fila["servicio"], "sam")
        self.assertGreater(fila["usd"], 0)
        self.assertEqual(meta_api.reservado_usd(), 0)

    def test_sam_respeta_el_tope_antes_de_subir_nada(self):
        with mock.patch.dict(os.environ, {"RETINA_TOPE_USD": "0"}), mock.patch.object(meta_api, "subir_archivo",
                                                                                      side_effect=AssertionError("subió")):
            with self.assertRaises(meta_api.TopeAlcanzado):
                sam.medir(Path(self.tmp.name), "flooded street")

    def test_sam_cobra_el_minimo_de_50_cuadros_aunque_el_clip_sea_mas_corto(self):
        async def vacio(*_):
            return types.SimpleNamespace(outcome=types.SimpleNamespace(status="completed"), records=[])
        with tempfile.TemporaryDirectory() as d, mock.patch.object(sam, "_correr"),                 mock.patch.object(meta_api, "subir_archivo", return_value="file-1"),                 mock.patch.object(meta_api, "borrar_archivo"), mock.patch.object(sam, "_segmentar", vacio),                 mock.patch.dict(sys.modules, {"meta_sam_parser": types.SimpleNamespace(decode_mask_to_raster=None)}):
            salida = sam.medir_imagen(Path(d) / "cuadro.png", "bread")
        self.assertEqual(salida["aparece"], False)
        self.assertAlmostEqual(self.filas()[0]["usd"], 0.01)

    def test_el_gasto_de_sam_queda_anotado_aunque_no_se_pueda_borrar_el_archivo(self):
        async def vacio(*_):
            return types.SimpleNamespace(outcome=types.SimpleNamespace(status="completed"), records=[])
        with tempfile.TemporaryDirectory() as d, mock.patch.object(sam, "_correr"), \
                mock.patch.object(meta_api, "subir_archivo", return_value="file-1"), \
                mock.patch.object(meta_api, "borrar_archivo", side_effect=RuntimeError("sin red")), \
                mock.patch.object(sam, "_segmentar", vacio), \
                mock.patch.dict(sys.modules, {"meta_sam_parser": types.SimpleNamespace(decode_mask_to_raster=None)}):
            with self.assertRaises(RuntimeError):
                sam.medir_imagen(Path(d) / "cuadro.png", "bread")
        self.assertEqual(self.filas()[0]["servicio"], "sam")
        self.assertEqual(meta_api.reservado_usd(), 0)

    def test_una_mascara_vacia_no_cuenta_como_que_se_ve(self):
        mascara = types.SimpleNamespace(width=2, height=2)
        registro = types.SimpleNamespace(kind="mask", frame=types.SimpleNamespace(frame_index=0), mask=mascara)

        async def vacia(*_):
            return types.SimpleNamespace(outcome=types.SimpleNamespace(status="completed"), records=[registro])
        with tempfile.TemporaryDirectory() as d, mock.patch.object(sam, "_correr"), \
                mock.patch.object(meta_api, "subir_archivo", return_value="file-1"), \
                mock.patch.object(meta_api, "borrar_archivo"), mock.patch.object(sam, "_segmentar", vacia), \
                mock.patch.dict(sys.modules, {"meta_sam_parser": types.SimpleNamespace(decode_mask_to_raster=lambda m: [0, 0, 0, 0])}):
            self.assertFalse(sam.medir_imagen(Path(d) / "cuadro.png", "bread")["aparece"])

    def test_varias_mascaras_en_un_cuadro_nunca_pasan_del_100_por_ciento(self):
        mascara = types.SimpleNamespace(width=2, height=2)
        registro = types.SimpleNamespace(kind="mask", frame=types.SimpleNamespace(frame_index=0), mask=mascara)

        async def dos(*_):
            return types.SimpleNamespace(outcome=types.SimpleNamespace(status="completed"), records=[registro, registro])
        with tempfile.TemporaryDirectory() as d, mock.patch.object(sam, "_correr"), \
                mock.patch.object(meta_api, "subir_archivo", return_value="file-1"), \
                mock.patch.object(meta_api, "borrar_archivo"), mock.patch.object(sam, "_segmentar", dos), \
                mock.patch.dict(sys.modules, {"meta_sam_parser": types.SimpleNamespace(decode_mask_to_raster=lambda m: [1, 1, 1, 1])}):
            self.assertEqual(sam.medir_imagen(Path(d) / "cuadro.png", "bread")["pct_maximo_del_cuadro"], 100.0)

    def test_una_imagen_tampoco_se_revisa_si_el_concepto_es_una_persona(self):
        with mock.patch.object(meta_api, "subir_archivo", side_effect=AssertionError("subió")):
            self.assertIn("error", sam.medir_imagen(Path(self.tmp.name) / "cuadro.png", "woman"))

    def test_el_registro_se_escribe_con_fsync(self):
        with mock.patch("os.fsync") as fsync:
            meta_api._registrar("prueba", "m", 1.0, 0.5)
        self.assertTrue(fsync.called)
        self.assertEqual(self.filas()[0]["usd"], 0.5)


# 8. Límites de llamadas del agente ------------------------------------------------------------------------------------

class CajaFalsa:
    def __init__(self):
        self.llamadas, self.por_turno = {}, []

    def correr(self, nombre, args):
        self.llamadas[nombre] = self.llamadas.get(nombre, 0) + 1
        return {"aceptada": True, "problemas": []} if nombre == "entregar_tarjeta" else {"ok": 1}


class ModeloDesbocado:
    """Pide `por_turno` llamadas distintas de golpe en cada turno; entrega la tarjeta en el turno `entrega` (si lo hay)."""

    def __init__(self, caja, herramienta, por_turno, entrega=None):
        self.caja, self.herramienta, self.por_turno, self.entrega = caja, herramienta, por_turno, entrega
        self.turnos, self.n, self.respuestas, self.insistencias = 0, 0, [], 0

    def turno(self):
        self.turnos += 1
        self.caja.por_turno.append(sum(v for k, v in self.caja.llamadas.items() if k != "entregar_tarjeta"))
        if self.entrega and self.turnos >= self.entrega:
            return [{"id": "e", "nombre": "entregar_tarjeta", "argumentos": json.dumps({"por_que": "listo"})}], ""
        llamadas = []
        for _ in range(self.por_turno):
            self.n += 1
            args = {"concepto": f"dog {self.n}"} if self.herramienta == "medir_lo_prometido" else {"desde_s": self.n, "hasta_s": self.n + 1}
            llamadas.append({"id": f"{self.turnos}-{self.n}", "nombre": self.herramienta, "argumentos": json.dumps(args)})
        return llamadas, ""

    def devolver(self, id_, salida):
        self.respuestas.append(salida)

    def insistir(self):
        self.insistencias += 1


class LimitesDelAgente(unittest.TestCase):
    def correr(self, herramienta, por_turno, entrega=None):
        caja = CajaFalsa()
        modelo = ModeloDesbocado(caja, herramienta, por_turno, entrega)
        return caja, modelo, agente.ciclo(caja, modelo)

    def test_las_constantes_son_claras(self):
        self.assertGreaterEqual(agente.MAX_LLAMADAS_TOTAL, agente.MAX_LLAMADAS_POR_TURNO)
        self.assertGreaterEqual(agente.MAX_LLAMADAS_POR_TURNO, 1)
        self.assertGreaterEqual(agente.MAX_LLAMADAS_SAM, 1)

    def test_un_modelo_desbocado_no_pasa_del_maximo_por_turno_ni_del_total(self):
        caja, modelo, (tarjeta_, _, _) = self.correr("ver_tramos", 20)  # antes: 240 llamadas en 12 turnos
        self.assertIsNone(tarjeta_)
        self.assertLessEqual(caja.llamadas["ver_tramos"], agente.MAX_LLAMADAS_TOTAL)
        pasos = [b - a for a, b in zip([0, *caja.por_turno], caja.por_turno)]
        self.assertLessEqual(max(pasos), agente.MAX_LLAMADAS_POR_TURNO)
        self.assertTrue(any("error" in r for r in modelo.respuestas))  # y se le dice por qué

    def test_sam_tiene_su_propio_tope_porque_cuesta(self):
        caja, _, _ = self.correr("medir_lo_prometido", 20)
        self.assertEqual(caja.llamadas["medir_lo_prometido"], agente.MAX_LLAMADAS_SAM)

    def test_al_llegar_al_limite_todavia_puede_cerrar_con_lo_que_tiene(self):
        caja, modelo, (tarjeta_, traza, falla) = self.correr("ver_tramos", 6, entrega=9)  # 8 turnos × 6 = 48 > 30
        self.assertEqual(tarjeta_, {"por_que": "listo"})
        self.assertIsNone(falla)
        self.assertEqual(caja.llamadas["ver_tramos"], agente.MAX_LLAMADAS_TOTAL)
        self.assertGreaterEqual(modelo.insistencias, 1)  # se le pidió entregar al agotar las consultas

    def test_entregar_la_tarjeta_nunca_se_bloquea_por_los_limites(self):
        caja, _, (tarjeta_, _, _) = self.correr("ver_tramos", 20, entrega=2)
        self.assertEqual(tarjeta_, {"por_que": "listo"})


# 9. Sí/no de la ficha ------------------------------------------------------------------------------------------------

class SiNoDeLaFicha(unittest.TestCase):
    CAMPOS = ["presenta_antes_del_tema", "tema_en_la_primera_frase", "promete_algo_visible", "cifra_al_inicio", "pide_interaccion"]

    def test_los_textos_falsos_son_falsos(self):
        for texto in ["false", "False", "FALSE", "no", "No", "0", "falso", " false ", "Falso"]:
            for campo in self.CAMPOS:
                with self.subTest(texto=texto, campo=campo):
                    self.assertIs(valida({**BUENA, campo: texto})[campo], False)

    def test_los_textos_verdaderos_son_verdaderos(self):
        for texto in ["true", "True", "sí", "Sí", "si", "yes", "YES", "1", "verdadero"]:
            with self.subTest(texto=texto):
                self.assertIs(valida({**BUENA, "cifra_al_inicio": texto})["cifra_al_inicio"], True)

    def test_los_booleanos_y_0_1_reales_se_respetan(self):
        self.assertIs(valida({**BUENA, "cifra_al_inicio": False})["cifra_al_inicio"], False)
        self.assertIs(valida({**BUENA, "cifra_al_inicio": True})["cifra_al_inicio"], True)
        self.assertIs(valida({**BUENA, "cifra_al_inicio": 0})["cifra_al_inicio"], False)
        self.assertIs(valida({**BUENA, "cifra_al_inicio": 1})["cifra_al_inicio"], True)

    def test_lo_que_no_se_entiende_invalida_la_ficha(self):
        for raro in ["tal vez", "", "2", 2, None, [], {}, "nope", 0.5, "null"]:
            with self.subTest(valor=raro):
                self.assertIsNone(valida({**BUENA, "pide_interaccion": raro}))

    def test_la_ficha_con_false_en_texto_ya_no_entra_al_numero_como_verdadera(self):
        from retina.ficha import ficha_a_vector
        a = ficha_a_vector(valida({**BUENA, "pide_interaccion": "false"}))
        b = ficha_a_vector(valida({**BUENA, "pide_interaccion": False}))
        self.assertEqual(list(a), list(b))


if __name__ == "__main__":
    unittest.main()
