"""Tests sin API ni datos privados: filtros, validador, SAM, tope y formato del panel.

Corren con:  python -m unittest discover -s tests   (desde la raíz del repo)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from retina import agente, explicar, integridad, meta_api  # noqa: E402
from retina.curvas import _grupo_lento, cubeta, grupo_parecido  # noqa: E402
from retina.sam import rechazo  # noqa: E402
from retina.transcribir import silencios  # noqa: E402


def ids(texto: str) -> list[str]:
    return [r["id"] for r in integridad.revisar(texto)]


class FiltroDeAnzuelos(unittest.TestCase):
    def test_atrapa_las_evasiones_de_la_auditoria(self):
        for texto in ["c0menten abajo", "co-menten", "сomenten", "pon 👍 si te gustó", "escriban su opinión",
                      "d4le l1ke", "mándalo al grupo de WhatsApp", "esto se cura en casa", "sorteo de un celular",
                      "no te vayas, al final te digo", "deja tu comentario"]:
            with self.subTest(texto=texto):
                self.assertTrue(ids(texto), f"debió bloquear: {texto}")

    def test_deja_pasar_las_sugerencias_normales(self):
        for texto in ["Pon el dato en pantalla desde el segundo 3", "Corta el silencio del segundo 3 al 8",
                      "el cura del pueblo", "pásalo al inicio", "deja tu explicación justo después de la fachada", "Adelanta la imagen de la pila de tortillas"]:
            with self.subTest(texto=texto):
                self.assertEqual(ids(texto), [], f"no debió bloquear: {texto}")

    def test_citar_un_anzuelo_para_quitarlo_no_cuenta(self):
        self.assertEqual(ids(explicar.sin_citas_a_quitar("Quita «compártelo con tu familia» del segundo 25")), [])
        self.assertTrue(ids(explicar.sin_citas_a_quitar("Di «comenta abajo» al inicio")))

    def test_senalar_el_anzuelo_que_dice_el_video_no_cuenta(self):
        datos = {"frases": [{"dice": "Soy veterinaria. Comparte esta información con todas las personas que tengan perros."}]}
        for texto in ("Ubica en el segundo 11.3 la frase «Comparte esta información con todas las personas que tengan perros».",
                      'Ubica el audio del segundo 11.3 donde empieza "Comparte esta información...".'):
            self.assertEqual(ids(explicar.sin_citas_a_quitar(texto, datos)), [], texto)

    def test_senalar_lo_que_el_video_no_dice_si_cuenta(self):
        self.assertTrue(ids(explicar.sin_citas_a_quitar("Ubica aquí y di: «comparte con todos tus amigos de la colonia».", {"frases": [{"dice": "Hola"}]})))


def tarjeta(**cambios) -> dict:
    t = dict(por_que="Del segundo 0.6 al 4.9 no se ve la pila de tortillas.", lo_que_funciona="",
             lo_bueno=["En el segundo 0.6 ya se ve la fila afuera de la tortillería."], lo_flojo=[],
             que_cambiar="Mueve el plano de la pila al segundo 0.", pasos=["Corta el plano de la pila y ponlo al inicio."],
             mejoras_opcionales=[], tipo_de_cambio="reordenar", momento_s=0.0,
             anzuelo_detectado="ninguno", anzuelo_frase="", anzuelo_momento_s=-1, confianza="media",
             storyboard=[], no_pude_verificar=[])
    t.update(cambios)
    return t


NUEVOS = ("lo_bueno", "lo_flojo", "mejoras_opcionales")
VERDE = dict(que_cambiar="", pasos=[], tipo_de_cambio="ninguno")  # nivel «bajo» sin anzuelo: sin cambio principal


DATOS = {"duracion_video_s": 90, "primer_cuarto_s": [2.2, 22.5], "nivel_de_riesgo": "alto", "tramos": [{"x": 4.9}, {"x": 0.6}]}


class Validador(unittest.TestCase):
    def test_tarjeta_limpia_pasa(self):
        self.assertEqual(explicar.revisar(tarjeta(), DATOS), [])

    def test_rechaza_jerga_y_cifras_internas(self):
        p = explicar.revisar(tarjeta(por_que="En el s0.6 se pierden 50.2 pp según ver_tramos."), DATOS)
        self.assertTrue(any("jerga" in x for x in p))
        self.assertTrue(any("cifras que no vienen" in x for x in p))

    def test_rechaza_porcentajes(self):
        self.assertTrue(explicar.revisar(tarjeta(por_que="Se va el 30 % de la gente en el segundo 4.9."), DATOS))

    def test_momento_fuera_del_arranque(self):
        self.assertTrue(any("fuera del arranque" in x for x in explicar.revisar(tarjeta(momento_s=60), DATOS)))

    def test_anzuelo_obliga_a_decir_donde_y_como_quitarlo(self):
        p = explicar.revisar(tarjeta(anzuelo_detectado="pide_interaccion", que_cambiar=""), DATOS)
        self.assertTrue(any("anzuelo_frase" in x for x in p))
        self.assertTrue(any("cómo quitarlo" in x for x in p))

    def test_valores_fuera_del_catalogo(self):
        self.assertTrue(any("no es un valor válido" in x for x in explicar.revisar(tarjeta(confianza="segura"), DATOS)))

    def test_texto_largo(self):
        self.assertTrue(any("caracteres" in x for x in explicar.revisar(tarjeta(por_que="a" * 300), DATOS)))

    def test_el_cambio_viene_en_pasos(self):
        self.assertTrue(any("pasos" in x for x in explicar.revisar(tarjeta(pasos=[]), DATOS)))
        self.assertTrue(any("paso 1" in x for x in explicar.revisar(tarjeta(pasos=["a" * 200]), DATOS)))
        self.assertTrue(explicar.revisar(tarjeta(pasos=["Pide que comenten abajo"]), DATOS))

    def test_citar_lo_que_el_video_ya_dice_para_quitarlo_pasa(self):
        # Casos reales del 28-oct: la tarjeta pedía quitar el anzuelo y el validador la tumbaba.
        datos = {**DATOS, "frases": [{"segundo": 4.9, "dice": "Comparte esta información con todas las "
                                                              "personas que tengan perritos en casa."}]}
        anzuelo = dict(anzuelo_detectado="pide_interaccion", anzuelo_momento_s=4.9,
                       anzuelo_frase="Comparte esta información con todas las personas que tengan perritos en casa")
        for que, paso in [
            ("Corta del segundo 0.6 al 4.9 donde te presentas y pides «Comparte esta información con todas las "
             "personas que tengan perritos en casa».", "Corta del segundo 0.6 al 4.9."),
            ("Quita el “Comparte esta información…” del segundo 4.9.", "Borra del audio “Comparte esta información…”."),
            ("Corta el pedido del segundo 4.9.", "Busca el segundo 4.9 y corta “Comparte esta información…”."),
        ]:
            with self.subTest(que=que):
                self.assertEqual(explicar.revisar(tarjeta(que_cambiar=que, pasos=[paso], **anzuelo), datos), [])
        # La transcripción repite palabras al tartamudear; la cita no tiene por qué.
        datos["frases"][0]["dice"] = "y comparte esta información con todas las personas que tengan perritos perritos en casa."
        que = "Corta del segundo 0.6 al 4.9 el pedido de “comparte esta información con todas las personas que tengan perritos en casa”."
        self.assertEqual(explicar.revisar(tarjeta(que_cambiar=que, **anzuelo), datos), [])

    def test_describir_el_anzuelo_con_otras_palabras_se_bloquea_y_dice_como_citarlo(self):
        p = explicar.revisar(tarjeta(que_cambiar="Corta el pedido de compartir del segundo 4.9.",
                                     anzuelo_detectado="pide_interaccion", anzuelo_frase="Comparte esto",
                                     anzuelo_momento_s=4.9), DATOS)
        self.assertTrue(any("cítalo entre «comillas»" in x for x in p))

    def test_citar_no_abre_la_puerta_a_un_anzuelo_nuevo(self):
        datos = {**DATOS, "frases": [{"segundo": 4.9, "dice": "Comparte esta información con tu familia."}]}
        for que in ["Corta el silencio del segundo 0.6 al 4.9 y al final di «comenta abajo»",
                    "Corta el silencio del segundo 0.6 y repite «Comparte esta información» al inicio",
                    "Mantén «Comparte esta información» en el segundo 4.9"]:
            with self.subTest(que=que):
                self.assertTrue(explicar.revisar(tarjeta(que_cambiar=que), datos))

    def test_intocables(self):
        self.assertTrue(explicar.toca_intocable("Muestra la lata sin pixelar desde el segundo 2"))

    # Lo bueno, lo flojo y mejoras opcionales (29-oct): la tarjeta verde casi no decía nada.
    def test_tarjeta_con_lo_bueno_lo_flojo_y_mejoras_pasa(self):
        t = tarjeta(lo_bueno=["En el segundo 0.6 ya se ve la fila.", "Del segundo 2.2 al 4.9 la voz dice el precio."],
                    lo_flojo=["En el segundo 4.9 la música tapa un poco la voz."],
                    mejoras_opcionales=["Baja la música del segundo 4.9 al 22.5 para que la voz se oiga clara."])
        self.assertEqual(explicar.revisar(t, DATOS), [])

    def test_en_verde_lo_flojo_y_las_mejoras_pueden_venir_vacios(self):
        verde = {**DATOS, "nivel_de_riesgo": "bajo"}
        self.assertEqual(explicar.revisar(tarjeta(**VERDE), verde), [])
        self.assertEqual(explicar.revisar(tarjeta(**VERDE, mejoras_opcionales=[
            "Pon el precio en pantalla desde el segundo 0.6."]), verde), [])  # la mejora no necesita cambio principal

    def test_lo_bueno_no_puede_venir_vacio(self):
        self.assertTrue(any("lo_bueno" in x for x in explicar.revisar(tarjeta(lo_bueno=[]), DATOS)))

    def test_a_lo_mas_tres_por_lista(self):
        for campo in NUEVOS:
            with self.subTest(campo=campo):
                p = explicar.revisar(tarjeta(**{campo: ["En el segundo 0.6 se ve la fila."] * 4}), DATOS)
                self.assertTrue(any(campo in x and "3" in x for x in p), p)

    def test_las_listas_nuevas_sin_jerga_ni_textos_largos(self):
        for campo, maximo in (("lo_bueno", 160), ("lo_flojo", 160), ("mejoras_opcionales", explicar.MAX_CARACTERES_PASO)):
            with self.subTest(campo=campo):
                self.assertEqual(explicar.revisar(tarjeta(**{campo: ["a" * maximo]}), DATOS), [])
                self.assertTrue(any("caracteres" in x for x in explicar.revisar(tarjeta(**{campo: ["a" * (maximo + 1)]}), DATOS)))
                p = explicar.revisar(tarjeta(**{campo: ["En el tramo 2 se va el 30 % de la gente."]}), DATOS)
                self.assertTrue(any("jerga" in x for x in p), p)

    def test_las_listas_nuevas_no_inventan_cifras(self):
        for campo in NUEVOS:
            with self.subTest(campo=campo):
                p = explicar.revisar(tarjeta(**{campo: ["En el segundo 7 se ve la pila de tortillas."]}), DATOS)
                self.assertTrue(any("cifras que no vienen" in x and "7" in x for x in p), p)

    def test_una_mejora_nunca_es_un_anzuelo_ni_toca_un_intocable(self):
        self.assertTrue(explicar.revisar(tarjeta(mejoras_opcionales=["Al final pide que comenten abajo."]), DATOS))
        p = explicar.revisar(tarjeta(mejoras_opcionales=["Quita el logo de la página del segundo 0.6."]), DATOS)
        self.assertTrue(any("intocable" in x for x in p), p)
        # Citar lo que el video ya dice para quitarlo sí se puede, igual que en los pasos.
        datos = {**DATOS, "frases": [{"segundo": 4.9, "dice": "Comparte esta información con tu familia."}]}
        self.assertEqual(explicar.revisar(tarjeta(mejoras_opcionales=[
            "Corta «Comparte esta información con tu familia» del segundo 4.9."]), datos), [])

    def test_lo_bueno_tampoco_elogia_un_anzuelo(self):
        self.assertTrue(explicar.revisar(tarjeta(lo_bueno=["En el segundo 4.9 pides que compartan y eso engancha."]), DATOS))
        # «lo_flojo» sí puede nombrarlo: describe lo que ya trae el video, como «por_que».
        self.assertEqual(explicar.revisar(tarjeta(lo_flojo=["En el segundo 4.9 pides que compartan."]), DATOS), [])

    def test_una_tarjeta_vieja_sin_campos_nuevos_no_truena(self):
        vieja = {k: v for k, v in tarjeta().items() if k not in NUEVOS}
        p = explicar.revisar(vieja, DATOS)  # sin KeyError: lo que falta cuenta como lista vacía
        self.assertTrue(any("lo_bueno" in x for x in p))
        self.assertFalse(any("lo_flojo" in x or "mejoras" in x for x in p))

    def test_una_lista_que_no_es_lista_se_rechaza(self):
        self.assertTrue(any("lista" in x for x in explicar.revisar(tarjeta(mejoras_opcionales="Sube la voz."), DATOS)))

    def test_el_esquema_pide_los_campos_nuevos(self):
        e = explicar.esquema()
        entrega = next(h for h in agente.HERRAMIENTAS if h["name"] == "entregar_tarjeta")["parameters"]
        for campo in NUEVOS:
            with self.subTest(campo=campo):
                self.assertIn(campo, e["required"])
                self.assertEqual(e["properties"][campo], {"type": "array", "items": {"type": "string"}})
                self.assertIn(campo, entrega["required"])

    def test_si_ninguna_pasa_el_validador_tampoco_quedan_mejoras(self):
        import tempfile
        from unittest import mock
        mala = tarjeta(por_que="a" * 300, mejoras_opcionales=["Pon el precio en pantalla desde el segundo 0.6."])
        intentos = [{"motor": "api", "sugerencia": mala["que_cambiar"], "problemas": ["«por_que» mide 300 caracteres"]}]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(explicar, "datos_del_arranque", return_value=DATOS), \
                mock.patch.object(explicar, "escribir", return_value=(mala, intentos, "api")):
            s = explicar.explicar(Path(d), {}, "api")
        self.assertEqual((s["que_cambiar"], s["pasos"], s["mejoras_opcionales"]), ("", [], []))

    def test_el_agente_no_deja_repetir_titulos_ajenos_en_lo_nuevo(self):
        caja = object.__new__(agente.Caja)
        caja.datos = DATOS
        caja.vistos = [{"videos": [{"titulo": "Así se hace el pan dulce más suave del mundo"}]}]
        for campo in NUEVOS:
            with self.subTest(campo=campo):
                r = caja.correr("entregar_tarjeta", tarjeta(**{campo: ["Como en Así se hace el pan dulce más suave del mundo."]}))
                self.assertTrue(any("título de otro video" in x for x in r["problemas"]), r)


class SparkOpenConRescate(unittest.TestCase):
    """«abierto+api»: Spark Open escribe la tarjeta; Spark 1.3 solo rescata la que el validador rechazó."""

    def escribir(self, respuestas: dict):
        llamadas = []

        def pedir(datos, aviso, motor):
            llamadas.append(motor)
            r = respuestas[motor]
            if isinstance(r, Exception):
                raise r
            return dict(r)
        salida, intentos, quien = explicar.escribir(DATOS, explicar.MOTORES["abierto+api"], pedir)
        return salida, intentos, quien, llamadas

    def test_si_spark_open_pasa_no_se_llama_a_spark_13(self):
        _, _, quien, llamadas = self.escribir({"abierto": tarjeta(), "api": tarjeta()})
        self.assertEqual((quien, llamadas), ("abierto", ["abierto"]))

    def test_spark_13_rescata_la_que_el_validador_rechaza_dos_veces(self):
        buena = tarjeta(que_cambiar="Pon el plano de la pila en el segundo 0.")
        salida, intentos, quien, llamadas = self.escribir({"abierto": tarjeta(por_que="a" * 300), "api": buena})
        self.assertEqual(llamadas, ["abierto", "abierto", "api"])
        self.assertEqual((quien, salida["que_cambiar"]), ("api", buena["que_cambiar"]))
        self.assertEqual([i["motor"] for i in intentos], ["abierto", "abierto", "api"])
        self.assertEqual(intentos[-1]["problemas"], [])

    def test_un_formato_invalido_de_spark_open_tambien_se_rescata(self):
        _, _, quien, llamadas = self.escribir({"abierto": RuntimeError("sin JSON"), "api": tarjeta()})
        self.assertEqual((quien, llamadas), ("api", ["abierto", "abierto", "api"]))
        self.assertTrue(explicar.toca_intocable("Corta del segundo 3 al 16 y quita el logo de la página"))
        self.assertTrue(explicar.toca_intocable("Quita la pregunta ¿Estás a favor? del final"))
        self.assertFalse(explicar.toca_intocable("Pon el dato en pantalla desde el segundo 0"))

    def pedidos_a_baseten(self, llamar) -> list[dict]:
        from unittest import mock
        from retina import baseten
        pedidos = []

        class Cliente:
            def __init__(self, **_):
                self.chat = self.completions = self

            def create(self, **kw):
                pedidos.append(kw)
                uso = mock.Mock(prompt_tokens=10, completion_tokens=5, prompt_tokens_details=None)
                mensaje = mock.Mock(content=json.dumps(tarjeta()), tool_calls=None)
                return mock.Mock(usage=uso, choices=[mock.Mock(message=mensaje)])
        # Sin openai instalado también corre (módulo falso) y con un registro de costos temporal: apartar el
        # gasto de la llamada escribe un archivo, y las pruebas no tocan el de quien las corre.
        import tempfile
        import types
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=Cliente)}), \
                mock.patch.dict(os.environ, {"RETINA_COSTOS": str(Path(d) / "costos.jsonl"),
                                             "RETINA_ENV": str(Path(d) / "no-hay.env")}), \
                mock.patch.object(baseten, "_llave", return_value="x"):
            llamar()
        return pedidos

    def test_la_tarjeta_de_una_vuelta_usa_el_razonamiento_de_fabrica(self):
        # Medido el 28-oct en 50 casos: con razonamiento alto no pasó más tarjetas a la primera (22 contra 28).
        pedidos = self.pedidos_a_baseten(lambda: explicar.pedir_abierto(DATOS, ""))
        self.assertNotIn("reasoning_effort", pedidos[0])

    def test_el_agente_en_spark_open_piensa_en_alto_y_recibe_las_herramientas(self):
        pedidos = self.pedidos_a_baseten(lambda: agente.ConSparkOpen("Revisa el arranque.").turno())
        self.assertEqual(pedidos[0]["reasoning_effort"], "high")
        self.assertEqual(len(pedidos[0]["tools"]), len(agente.HERRAMIENTAS))


class AgenteEnSparkOpen(unittest.TestCase):
    """El agente corre en Spark Open (pesos abiertos); Spark 1.3 solo rescata si el ciclo no cierra."""

    class Caja:
        def correr(self, nombre, args):
            ok = args.get("por_que") != "mala"
            return {"aceptada": ok, "problemas": [] if ok else ["la tarjeta no pasa"]}

    class Guion:
        """Un modelo de mentira que entrega, en orden, las tarjetas que se le dan."""

        def __init__(self, *tarjetas):
            self.tarjetas, self.turnos = list(tarjetas), 0

        def turno(self):
            self.turnos += 1
            if not self.tarjetas:
                return [], "ya no sé qué más hacer"
            return [{"id": str(self.turnos), "nombre": "entregar_tarjeta", "argumentos": json.dumps(self.tarjetas.pop(0))}], ""

        def devolver(self, id_, salida):
            pass

        def insistir(self):
            pass

    def investigar(self, abierto, api):
        return agente.investigar(self.Caja(), agente.MOTORES["abierto+api"], {"abierto": lambda: abierto, "api": lambda: api})

    def test_si_el_ciclo_de_spark_open_cierra_spark_13_no_trabaja(self):
        api = self.Guion({"por_que": "buena"})
        tarjeta, _, quien, _ = self.investigar(self.Guion({"por_que": "buena"}), api)
        self.assertEqual((quien, tarjeta["por_que"], api.turnos), ("abierto", "buena", 0))

    def test_spark_13_rescata_cuando_spark_open_no_cierra(self):
        abierto, api = self.Guion({"por_que": "mala"}), self.Guion({"por_que": "buena"})
        _, traza, quien, _ = self.investigar(abierto, api)
        self.assertEqual((quien, abierto.turnos, api.turnos), ("api", agente.MAX_TURNOS, 1))
        self.assertEqual([t["motor"] for t in traza if "herramienta" in t], ["abierto", "api"])

    def test_una_falla_de_red_de_spark_open_pasa_al_rescate(self):
        class Caido(self.Guion):
            def turno(self):
                raise ConnectionError("sin red")
        _, _, quien, fallas = self.investigar(Caido(), self.Guion({"por_que": "buena"}))
        self.assertEqual(quien, "api")
        self.assertIn("ConnectionError", fallas[0])

    def test_spark_open_recibe_las_mismas_herramientas_en_formato_de_chat(self):
        self.assertEqual({h["function"]["name"] for h in agente.HERRAMIENTAS_CHAT}, agente.NOMBRES)

    def test_por_omision_el_agente_corre_en_spark_open_con_rescate(self):
        # Medido el 28-oct en 50 casos: el agente en Spark Open cerró los 50 sin rescate.
        self.assertEqual(explicar.MOTOR_POR_OMISION, "abierto+api")

    def test_el_motor_por_omision_sale_del_env_al_usarse(self):
        from unittest import mock
        sin_archivo = {"RETINA_ENV": str(RAIZ / "no-existe.env")}
        with mock.patch.dict(os.environ, {**sin_archivo, "RETINA_MOTOR": "api"}):
            self.assertEqual(explicar.motor_por_omision(), "api")
        with mock.patch.dict(os.environ, sin_archivo):
            os.environ.pop("RETINA_MOTOR", None)
            self.assertEqual(explicar.motor_por_omision(), explicar.MOTOR_POR_OMISION)
        with mock.patch.dict(os.environ, {**sin_archivo, "RETINA_MOTOR": "gpt"}), self.assertRaises(ValueError):
            explicar.motor_por_omision()


class Sam(unittest.TestCase):
    def test_nunca_personas(self):
        for c in ["girls", "persons", "hombres", "dancer", "hands", "paramedic in red vest", "veterinaria",
                  "nurse", "firefighter", "worker", "red dress"]:
            with self.subTest(concepto=c):
                self.assertIsNotNone(rechazo(c))

    def test_objetos_y_lugares_si(self):
        for c in ["flooded street", "stack of tortillas", "sweet bread", "dog", "landslides"]:
            with self.subTest(concepto=c):
                self.assertIsNone(rechazo(c))


class Silencios(unittest.TestCase):
    def test_huecos_al_inicio_en_medio_y_al_final(self):
        turnos = [{"startMs": 4000, "endMs": 6000}, {"startMs": 6500, "endMs": 8000}, {"startMs": 12000, "endMs": 13000}]
        self.assertEqual(silencios(turnos, 20000), [{"inicio_ms": 0, "fin_ms": 4000}, {"inicio_ms": 8000, "fin_ms": 12000},
                                                    {"inicio_ms": 13000, "fin_ms": 20000}])


class ReglaDeParecidos(unittest.TestCase):
    def test_el_indice_rapido_da_lo_mismo_que_la_definicion(self):
        azar = np.random.default_rng(7)
        inicio, filas = datetime(2026, 1, 1), []
        for i in range(400):
            dur = float(azar.choice([20, 45, 90, 180, 400]))
            filas.append({"codigo": f"P{i}", "fecha": inicio + timedelta(hours=int(azar.integers(0, 24 * 200))),
                          "dur": dur, "cubeta": cubeta(dur), "talento": str(azar.choice(["ANA", "LUIS", ""])),
                          "curva": np.sort(azar.random(41))[::-1]})
        filas.sort(key=lambda x: x["fecha"])
        for v in filas[::23]:
            with self.subTest(codigo=v["codigo"]):
                a, b = grupo_parecido(v, filas, filas), _grupo_lento(v, filas, filas)
                self.assertEqual(a[1], b[1]); self.assertEqual(a[2], b[2])
                np.testing.assert_allclose(a[0], b[0], atol=1e-9)

    def test_un_video_subido_que_ya_esta_en_el_entrenamiento_no_se_cuenta_a_si_mismo(self):
        # Un video ya publicado que se sube para revisarlo llega sin curva, pero su fila sí está entre los
        # que aprendió el modelo: hay que sacar esa fila de sus parecidos, no tronar (pasó el 28-oct).
        azar = np.random.default_rng(11)
        inicio, filas = datetime(2025, 1, 1), []
        for i in range(300):
            dur = float(azar.choice([45, 90]))
            filas.append({"codigo": f"P{i}", "fecha": inicio + timedelta(hours=int(azar.integers(0, 24 * 300))),
                          "dur": dur, "cubeta": cubeta(dur), "talento": str(azar.choice(["ANA", "LUIS"])),
                          "curva": np.sort(azar.random(41))[::-1]})
        filas.sort(key=lambda x: x["fecha"])
        for h in filas[::37]:
            subido = {k: h[k] for k in ("codigo", "fecha", "dur", "cubeta", "talento")}  # sin «curva»
            subido["fecha"] = h["fecha"] + timedelta(days=400)  # ya fuera de la ventana de 90 días
            with self.subTest(codigo=h["codigo"]):
                a, b = grupo_parecido(subido, filas, filas), _grupo_lento(subido, filas, filas)
                self.assertEqual(a[1:], b[1:])
                np.testing.assert_allclose(a[0], b[0], atol=1e-9)


class Tope(unittest.TestCase):
    def test_el_env_no_sube_el_tope_maximo(self):
        antes = os.environ.get("RETINA_TOPE_USD")
        os.environ["RETINA_TOPE_USD"] = "1000"
        try:
            self.assertEqual(meta_api.tope_usd(), meta_api.TOPE_MAXIMO_USD)
        finally:
            if antes is None:
                os.environ.pop("RETINA_TOPE_USD")
            else:
                os.environ["RETINA_TOPE_USD"] = antes

    def test_peor_caso_cuenta_toda_la_salida(self):
        self.assertAlmostEqual(meta_api.peor_caso_usd({"model": "muse-spark-1.3", "max_output_tokens": 16000}), 0.068)


class FormatoDelPanel(unittest.TestCase):
    def test_el_ejemplo_trae_lo_que_lee_el_panel(self):
        r = json.loads((RAIZ / "casos" / "demo" / "resultado.json").read_text(encoding="utf-8"))
        # El ejemplo se ve como Retina de fábrica: con el número y sin semáforo (docs/decisiones.md).
        self.assertEqual(r["arranque"]["nivel"], "sin_nivel")
        self.assertEqual((r["licencia"]["cerebro"], r["licencia"]["conoce_al_creador"]), ("cualquier_video", False))
        self.assertEqual(len(r["prediccion"]["curva_predicha"]), 41)
        self.assertEqual(len(r["prediccion"]["curva_parecidos"]), 41)
        self.assertTrue(r["ficha"]["gancho"])
        for campo in explicar.esquema()["required"]:
            self.assertIn(campo, r["explicacion"])
        for campo in ("comparado_con", "datos_hasta", "no_pude_revisar"):
            self.assertIn(campo, r["licencia"])

    def test_el_ejemplo_trae_su_apertura_comprobada_y_sus_dibujos(self):
        for caso in ("demo", "demo-en"):
            with self.subTest(caso=caso):
                carpeta = RAIZ / "casos" / caso
                r = json.loads((carpeta / "resultado.json").read_text(encoding="utf-8"))
                a = r["apertura"]
                self.assertTrue(a["aprobada"])
                self.assertEqual(a["titulo"], r["video"]["titulo"])
                self.assertTrue(all(c["paso"] for c in a["comprobaciones"]))
                self.assertIn("promesa", {c["id"] for c in a["comprobaciones"]})
                for nombre in [a["antes"]["imagen"], *a["despues"]["imagenes"]]:
                    self.assertTrue((carpeta / nombre).is_file(), nombre)
                    self.assertTrue(nombre.endswith(".webp"))

    def test_el_ejemplo_trae_la_revision_segun_meta_con_su_fuente(self):
        r = json.loads((RAIZ / "casos" / "demo" / "resultado.json").read_text(encoding="utf-8"))
        reglas = {x["id"]: x for x in json.loads((RAIZ / "reglas" / "recomendaciones-meta-v1.json").read_text(encoding="utf-8"))["reglas"]}
        self.assertTrue(r["revision_meta"])
        for x in r["revision_meta"]:
            with self.subTest(id=x["id"]):
                self.assertEqual({k: x[k] for k in ("ventana", "regla", "fuente")},
                                 {k: reglas[x["id"]][k] for k in ("ventana", "regla", "fuente")})
                self.assertIn(x["cumple"], (True, False, None))
                self.assertTrue(x["evidencia"].strip())

    def test_el_panel_no_usa_campos_retirados_ni_inner_html(self):
        panel = (RAIZ / "panel" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("tramo_riesgo", panel)
        self.assertNotIn("innerHTML", panel)
        self.assertIn("arranque.nivel", panel.replace("a.nivel", "arranque.nivel"))

    def test_el_ejemplo_pasa_el_validador(self):
        r = json.loads((RAIZ / "casos" / "demo" / "resultado.json").read_text(encoding="utf-8"))
        datos = {"duracion_video_s": r["video"]["duracion_s"], "primer_cuarto_s": [2.4, 24.0],
                 "nivel_de_riesgo": r["arranque"]["nivel"],
                 # el ejemplo es inventado: sus segundos hacen de «lo que vio el modelo»
                 "vistos": [r["explicacion"]["por_que"], r["explicacion"]["lo_que_funciona"]]}
        self.assertEqual(explicar.revisar(r["explicacion"], datos), [])


class Demo(unittest.TestCase):
    def test_la_demo_solo_sirve_el_panel_y_los_casos(self):
        from retina.demo import PERMITIDO
        for ruta in ("/panel/", "/panel/index.html", "/casos/demo/resultado.json"):
            self.assertTrue(PERMITIDO.match(ruta), ruta)

    def test_la_demo_sirve_los_fondos_del_panel_y_nada_mas(self):
        from retina.demo import CASO, PERMITIDO, SoloElPanel
        for ruta in ("/panel/fondos/fondo-oceano.webp", "/panel/fondos/mini-cinta.webp"):
            self.assertTrue(PERMITIDO.match(ruta), ruta)
        for ruta in ("/panel/fondos/../../.env", "/panel/fondos/fondo-x.png", "/src/retina/demo.py", "/.git/config"):
            self.assertFalse(PERMITIDO.match(ruta), ruta)
        self.assertFalse(CASO.match("/panel/fondos/fondo-oceano.webp"))  # --caso solo acepta un resultado.json
        self.assertEqual(SoloElPanel.extensions_map[".webp"], "image/webp")
        for ruta in ("/.git/config", "/README.md", "/casos/", "/casos/../.env", "/src/retina/meta_api.py"):
            self.assertFalse(PERMITIDO.match(ruta), ruta)

    def test_el_repo_no_sirve_paginas_privadas(self):
        # La galería de casos reales vive fuera del repo; subir un video se hace en el mismo panel.
        from retina.demo import PERMITIDO
        for ruta in ("/panel/galeria.html", "/panel/subir.html", "/casos/indice.json", "/casos/otro.json",
                     "/casos/x/indice.json"):
            self.assertFalse(PERMITIDO.match(ruta), ruta)

    def test_con_una_carpeta_privada_los_casos_salen_de_ahi_y_de_nada_mas(self):
        from retina.demo import ruta_local
        privada = Path("D:/privado/casos")
        self.assertEqual(ruta_local("/casos/ABC1/resultado.json", RAIZ, privada), privada / "ABC1" / "resultado.json")
        self.assertEqual(ruta_local("/panel/index.html", RAIZ, privada), RAIZ / "panel" / "index.html")
        self.assertEqual(ruta_local("/casos/demo/resultado.json", RAIZ, None), RAIZ / "casos" / "demo" / "resultado.json")
        for ruta in ("/casos/../.env", "/casos/%2e%2e/x/resultado.json", "/.git/config"):
            self.assertIsNone(ruta_local(ruta, RAIZ, privada), ruta)

    def test_la_demo_sirve_las_ilustraciones_del_storyboard_de_un_caso(self):
        from retina.demo import PERMITIDO
        self.assertTrue(PERMITIDO.match("/casos/demo/agente-cuadro1-ilustracion-ia.webp"))
        self.assertTrue(PERMITIDO.match("/casos/demo/explicar-cuadro3-ilustracion-ia.png"))
        for ruta in ("/casos/demo/foto.png", "/casos/demo/agente-cuadro1-ilustracion-ia.svg",
                     "/casos/demo/../x-ilustracion-ia.png", "/casos/demo/sub/x-ilustracion-ia.png"):
            self.assertFalse(PERMITIDO.match(ruta), ruta)


class SubirUnVideo(unittest.TestCase):
    """retina.app: sube un video y recibe la tarjeta (prototipo local)."""

    def datos(self, **cambios):
        from urllib.parse import quote
        h = {"X-Retina-Titulo": quote("Fresas de prueba llegan a Canadá"), "X-Retina-Talento": quote("ÁNGELA DE PRUEBA"),
             "X-Retina-Codigo": "XYZ0000001", "X-Retina-Fecha": "2026-01-15 18:00", "X-Retina-Publicado": "1"}
        h.update(cambios)
        return h

    def test_los_datos_buenos_se_leen_con_acentos(self):
        from retina.app import leer_datos
        d = leer_datos(self.datos())
        self.assertEqual((d["talento"], d["codigo"], d["fecha"], d["publicado"]),
                         ("ÁNGELA DE PRUEBA", "XYZ0000001", "2026-01-15 18:00", True))

    def test_un_video_sin_codigo_ni_talento_se_acepta(self):
        # Un video de otra cuenta no trae código de producción; su título no se parte letra por letra.
        from retina.agente import titulo_limpio
        from retina.app import leer_datos
        from retina.predecir import palabras_titulo
        d = leer_datos(self.datos(**{"X-Retina-Codigo": "", "X-Retina-Talento": "", "X-Retina-Publicado": "0"}))
        self.assertEqual((d["codigo"], d["talento"], d["publicado"]), ("", "", False))
        self.assertEqual(palabras_titulo("Fresas de prueba llegan", ""), ["fresas", "prueba", "llegan"])
        self.assertEqual(titulo_limpio("Fresas de prueba llegan", ""), "Fresas de prueba llegan")

    def test_los_datos_raros_se_rechazan(self):
        from retina.app import leer_datos
        for cambio in ({"X-Retina-Fecha": "ayer"}, {"X-Retina-Codigo": "../x"}, {"X-Retina-Titulo": "a" * 301},
                       {"X-Retina-Titulo": ""}, {"X-Retina-Talento": "a" * 81}):
            with self.subTest(cambio=cambio), self.assertRaises(ValueError):
                leer_datos(self.datos(**cambio))

    def test_solo_acepta_mp4(self):
        from retina.app import es_mp4
        self.assertTrue(es_mp4(b"\x00\x00\x00\x18ftypmp42\x00\x00"))
        self.assertFalse(es_mp4(b"<html><script>alert(1)"))

    def test_solo_acepta_pedidos_de_su_propia_pagina(self):
        from retina.app import pedido_propio
        self.assertTrue(pedido_propio({"X-Retina": "1", "Origin": "http://127.0.0.1:8790"}, 8790))
        self.assertTrue(pedido_propio({"X-Retina": "1"}, 8790))
        self.assertFalse(pedido_propio({"Origin": "http://127.0.0.1:8790"}, 8790))  # sin la cabecera propia
        self.assertFalse(pedido_propio({"X-Retina": "1", "Origin": "https://otro-sitio.com"}, 8790))

    def test_un_tamano_mal_formado_se_rechaza(self):
        from retina.app import largo_valido
        self.assertEqual(largo_valido("1048576"), 1048576)
        for malo in (None, "", "abc", "-5", "1e9", "12 34"):
            self.assertIsNone(largo_valido(malo), malo)

    def test_el_avance_se_escribe_completo_o_no_se_escribe(self):
        import tempfile
        from retina.app import _escribir_estado
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            _escribir_estado(d, estado="error", mensaje="algo")
            self.assertEqual(json.loads((d / "estado.json").read_text(encoding="utf-8"))["estado"], "error")
            self.assertEqual(sorted(x.name for x in d.iterdir()), ["estado.json"])  # sin temporales sueltos

    def test_el_avance_sale_de_lo_que_ya_se_escribio(self):
        import tempfile
        from retina.app import estado
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.assertEqual(estado(d), {"estado": "en_fila"})
            (d / "estado.json").write_text('{"estado": "procesando"}', encoding="utf-8")
            self.assertEqual(estado(d), {"estado": "procesando", "paso": "cortando"})
            (d / "manifiesto.json").write_text("{}", encoding="utf-8")
            self.assertEqual(estado(d)["paso"], "escuchando")
            (d / "estado.json").write_text('{"estado": "error", "mensaje": "El candado está encendido"}', encoding="utf-8")
            self.assertEqual(estado(d), {"estado": "error", "mensaje": "El candado está encendido"})


class StoryboardEnElPanel(unittest.TestCase):
    """Las ilustraciones de Muse Image se anotan en el resultado.json del caso para que el panel las muestre."""

    def anotar(self, storyboard_del_caso, storyboard_dibujado):
        import tempfile
        from retina import storyboard
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "resultado.json").write_text(json.dumps({"explicacion": {"storyboard": storyboard_del_caso}}), encoding="utf-8")
            storyboard.anotar(d, storyboard_dibujado, [d / "agente-cuadro1-ilustracion-ia.png"])
            return json.loads((d / "resultado.json").read_text(encoding="utf-8"))["explicacion"]

    def test_las_ilustraciones_quedan_anotadas_en_el_caso(self):
        e = self.anotar(["dos panes"], ["dos panes"])
        self.assertEqual(e["storyboard_imagenes"], ["agente-cuadro1-ilustracion-ia.png"])

    def test_si_son_de_otra_tarjeta_no_se_anotan(self):
        self.assertNotIn("storyboard_imagenes", self.anotar(["dos panes"], ["una báscula"]))

    def test_sin_resultado_no_se_crea_nada(self):
        import tempfile
        from retina import storyboard
        with tempfile.TemporaryDirectory() as d:
            storyboard.anotar(Path(d), ["a"], [Path(d) / "x-ilustracion-ia.png"])
            self.assertEqual(list(Path(d).iterdir()), [])


class RevisionMeta(unittest.TestCase):
    def test_cada_recomendacion_trae_su_fuente_de_meta(self):
        reglas = json.loads((RAIZ / "reglas" / "recomendaciones-meta-v1.json").read_text(encoding="utf-8"))["reglas"]
        self.assertGreaterEqual(len(reglas), 5)
        for r in reglas:
            self.assertRegex(r["fuente"], r"^https://(www\.facebook\.com|creators\.facebook\.com)/")

    def test_sin_datos_no_inventa(self):
        from retina.revision_meta import revisar
        self.assertEqual(revisar(Path("no-existe")), [])


class SoloPublicados(unittest.TestCase):
    def setUp(self):
        self.antes = os.environ.get("RETINA_SOLO_PUBLICADOS")

    def tearDown(self):
        if self.antes is None:
            os.environ.pop("RETINA_SOLO_PUBLICADOS", None)
        else:
            os.environ["RETINA_SOLO_PUBLICADOS"] = self.antes

    def test_con_candado_sin_confirmar_publicado_no_va_a_meta(self):
        from retina.retina import correr
        os.environ["RETINA_SOLO_PUBLICADOS"] = "1"
        with self.assertRaises(ValueError):
            correr(Path("no-existe.mp4"), Path("m.pkl"), Path("salida"), "X", "", "2026-10-28 10:00", "", True,
                   Path("a.json"), publicado=False)

    def test_el_candado_viene_apagado_y_se_prende_con_uno(self):
        from retina.retina import solo_publicados
        os.environ["RETINA_SOLO_PUBLICADOS"] = ""
        self.assertFalse(solo_publicados())  # vacío = lo de por omisión: apagado
        os.environ["RETINA_SOLO_PUBLICADOS"] = "1"
        self.assertTrue(solo_publicados())


class CerebroParaCualquierVideo(unittest.TestCase):
    """Un video de fuera (sin talento ni tipo conocidos) usa lo que trae cualquier video; los de la casa, la v0."""

    @classmethod
    def setUpClass(cls):
        from retina.predecir import Modelo
        azar = np.random.default_rng(29)
        inicio, filas, voz = datetime(2025, 1, 1), [], {}
        for i in range(240):
            dur = float(azar.choice([45, 90, 180]))
            filas.append({"codigo": f"XYZ{i:04d}", "fecha": inicio + timedelta(hours=int(azar.integers(0, 24 * 300))),
                          "dur": dur, "cubeta": cubeta(dur), "talento": str(azar.choice(["ANA", "LUIS"])),
                          "archivo": f"2025-01-01 XYZ{i:04d} ANA NOTA EDITOR receta casera", "titulo": "receta casera",
                          "reel": float(dur < 60), "curva": np.sort(azar.random(41))[::-1]})
            if i % 2:
                voz[f"XYZ{i:04d}"] = [[0.5, "hola qué tal"], [3.0, "hoy te enseño una receta"]]
        filas.sort(key=lambda x: x["fecha"])
        cls.modelo = Modelo.entrenar(filas, voz=voz)
        cls.tramos = [[0.3, "¿Sabías esto?"], [2.0, "Te lo cuento"], [31.0, "Al final"]]

    def video(self, **cambios):
        v = {"fecha": datetime(2025, 12, 1, 18), "dur": 90.0, "cubeta": cubeta(90.0), "codigo": "", "talento": "",
             "archivo": "receta de la abuela", "titulo": "receta de la abuela", "reel": 0.0}
        return {**v, **cambios}

    def test_un_video_de_fuera_con_voz_usa_el_cerebro_para_cualquier_video(self):
        r = self.modelo.predecir(self.video(), tramos=self.tramos)
        self.assertEqual((r["cerebro"], r["conoce_al_creador"], r["uso_voz"]), ("cualquier_video", False, True))
        self.assertEqual(len(r["curva_predicha"]), 41)
        self.assertTrue(all(0 <= x <= 1 for x in r["curva_predicha"]))

    def test_un_video_de_la_casa_sigue_con_la_v0_aunque_traiga_voz(self):
        for cambios in ({"talento": "ANA"}, {"codigo": "XYZ9999"}):
            with self.subTest(**cambios):
                r = self.modelo.predecir(self.video(**cambios), tramos=self.tramos)
                self.assertEqual((r["cerebro"], r["conoce_al_creador"]), ("casa", True))

    def test_de_fuera_sin_voz_se_queda_en_la_v0_y_lo_dice(self):
        r = self.modelo.predecir(self.video())
        self.assertEqual((r["cerebro"], r["conoce_al_creador"]), ("casa", False))

    def test_de_fuera_no_usa_el_nombre_de_archivo_de_la_casa(self):
        from retina.predecir import de_fuera
        v = de_fuera({"titulo": "", "archivo": "2025-01-01 XYZ0001 ANA NOTA EDITOR", "talento": "ANA", "codigo": "XYZ0001"})
        self.assertEqual((v["archivo"], v["talento"], v["codigo"]), ("", "", ""))

    def test_la_voz_frase_por_frase_se_junta_como_la_del_entrenamiento(self):
        from retina.voz import en_bloques
        self.assertEqual(en_bloques([[29.0, "c"], [0.2, "a"], [3.0, "b"]]), [[0.2, "a b"], [29.0, "c"]])

    def test_un_reel_se_reconoce_por_el_primer_cuadro(self):
        import tempfile
        from retina.retina import es_vertical
        app0 = bytes([0xFF, 0xE0]) + (16).to_bytes(2, "big") + bytes(14)
        for alto, ancho, esperado in ((502, 256, 1.0), (256, 456, 0.0)):
            with self.subTest(alto=alto, ancho=ancho), tempfile.TemporaryDirectory() as d:
                (Path(d) / "cuadros").mkdir()
                cabeza = bytes([0xFF, 0xC0]) + (17).to_bytes(2, "big") + bytes([8])
                sof = cabeza + alto.to_bytes(2, "big") + ancho.to_bytes(2, "big") + bytes(10)
                (Path(d) / "cuadros" / "c00001.jpg").write_bytes(bytes([0xFF, 0xD8]) + app0 + sof)
                self.assertEqual(es_vertical(Path(d)), esperado)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(es_vertical(Path(d)), 0.0)  # sin cuadros no se supone reel


class CualquierFormato(unittest.TestCase):
    """Un juez puede subir un .mov del celular o un .webm: se acepta por su contenido y se pasa a MP4."""

    def test_se_reconoce_el_video_por_su_contenido(self):
        from retina.app import tipo_de_video
        caja = lambda t: bytes(4) + t + bytes(4)  # noqa: E731
        self.assertEqual(tipo_de_video(caja(b"ftyp")), "mp4")          # MP4 y MOV modernos
        self.assertEqual(tipo_de_video(caja(b"wide")), "convertir")    # MOV viejo
        self.assertEqual(tipo_de_video(bytes([0x1A, 0x45, 0xDF, 0xA3]) + bytes(8)), "convertir")  # WebM y MKV
        self.assertEqual(tipo_de_video(b"RIFF" + bytes(4) + b"AVI "), "convertir")
        for no in (b"<html><script>", b"%PDF-1.7 xxxx", bytes([0x89, 0x50, 0x4E, 0x47]) + bytes(8), b"corto"):
            with self.subTest(no=no):
                self.assertIsNone(tipo_de_video(no))

    def test_la_version_a_puede_estar_todavia_sin_convertir(self):
        import tempfile
        from retina.app import SUBIDA, comparar_con
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a1b2c3d4e5f6").mkdir()
            (Path(d) / "a1b2c3d4e5f6" / SUBIDA).write_bytes(b"x")
            self.assertEqual(comparar_con({"X-Retina-Comparar-Con": "a1b2c3d4e5f6"}, Path(d)).name, "a1b2c3d4e5f6")

    @unittest.skipUnless(os.environ.get("FFMPEG") or __import__("shutil").which("ffmpeg"), "sin ffmpeg")
    def test_un_webm_queda_como_mp4(self):
        import subprocess
        import tempfile
        from retina.app import convertir_a_mp4, es_mp4
        from retina.segmentar import _ffmpeg
        with tempfile.TemporaryDirectory() as d:
            webm = Path(d) / "x.webm"
            subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10",
                            "-t", "1", "-c:v", "libvpx-vp9", str(webm)], check=True)
            convertir_a_mp4(webm, Path(d) / "video.mp4")
            self.assertTrue(es_mp4((Path(d) / "video.mp4").read_bytes()[:12]))
            with self.assertRaises(ValueError):
                (Path(d) / "roto.webm").write_bytes(b"no es video")
                convertir_a_mp4(Path(d) / "roto.webm", Path(d) / "otro.mp4")


class IdiomaDeLaTarjeta(unittest.TestCase):
    """Un juez que usa el panel en inglés recibe la tarjeta en inglés."""

    def test_el_panel_pide_ingles_y_cualquier_otra_cosa_es_espanol(self):
        from retina.app import leer_datos
        base = {"X-Retina-Titulo": "Hola", "X-Retina-Fecha": "2026-10-30 18:00"}
        self.assertEqual(leer_datos({**base, "X-Retina-Idioma": "en"})["idioma"], "en")
        for otro in ("", "fr", "en; x"):
            with self.subTest(otro=otro):
                self.assertEqual(leer_datos({**base, "X-Retina-Idioma": otro})["idioma"], "es")

    def test_las_frases_de_meta_existen_en_los_dos_idiomas(self):
        from retina.revision_meta import FRASES, GANCHOS, GANCHOS_EN
        self.assertEqual(set(FRASES["es"]), set(FRASES["en"]))
        self.assertEqual(set(GANCHOS), set(GANCHOS_EN))

    def test_cada_regla_de_meta_trae_su_titulo_en_ingles(self):
        reglas = json.loads((RAIZ / "reglas" / "recomendaciones-meta-v1.json").read_text(encoding="utf-8"))["reglas"]
        self.assertTrue(all(r.get("regla_en") for r in reglas))


class PlanBSoloModelosDeMeta(unittest.TestCase):
    """Si la ridge contara como modelo que no es de Meta: sin fórmula, sin nivel, y la tarjeta lo dice."""

    def pred(self):
        base = list(np.linspace(1, 0.2, 41))
        return {"curva_predicha": list(np.linspace(1, 0.3, 41)), "curva_parecidos": base, "tramo_riesgo": 7,
                "caida_predicha_pp": 3.0, "caida_parecidos_pp": 2.0, "regla_de_parecidos": "publica", "n_parecidos": 210,
                "uso_video": True, "cerebro": "cualquier_video", "conoce_al_creador": False, "uso_voz": True,
                "datos_hasta": "2026-10-24"}

    def test_la_curva_queda_en_el_promedio_y_sin_nivel(self):
        from retina.retina import licencia, sin_formula, sin_nivel
        p = sin_formula(self.pred())
        self.assertEqual(p["curva_predicha"], p["curva_parecidos"])
        self.assertEqual((p["cerebro"], p["uso_voz"], p["uso_video"]), ("promedio", False, False))
        a = sin_nivel(p)
        self.assertEqual((a["nivel"], len(a["bloques"])), ("sin_nivel", 5))
        self.assertTrue(licencia(p, [])["sin_formula"])

    def test_de_fabrica_el_numero_va_prendido_y_se_apaga_con_un_1(self):
        from retina.retina import solo_modelos_meta
        antes = os.environ.pop("RETINA_SOLO_MODELOS_META", None)
        try:
            with mock.patch("retina.meta_api._cargar_env"):
                self.assertFalse(solo_modelos_meta())
                os.environ["RETINA_SOLO_MODELOS_META"] = "1"; self.assertTrue(solo_modelos_meta())
                os.environ["RETINA_SOLO_MODELOS_META"] = "0"; self.assertFalse(solo_modelos_meta())
        finally:
            os.environ.pop("RETINA_SOLO_MODELOS_META", None)
            if antes is not None:
                os.environ["RETINA_SOLO_MODELOS_META"] = antes

    def test_el_cerebro_publico_no_necesita_v_jepa(self):
        from retina import retina as r
        modelo = mock.Mock(semaforo=False)
        modelo.predecir.return_value = self.pred()
        modelo.arranque.return_value.predecir.return_value = {"nivel": "medio", "bloques": []}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(r, "segmentar", return_value={"duracion_s": 60.0}), \
                mock.patch.object(r, "preparar_carpeta"), mock.patch.object(r, "solo_modelos_meta", return_value=False), \
                mock.patch("retina.publico.cargar_modelo", return_value=modelo):
            archivo = Path(d) / "modelo.json"
            archivo.write_text("{}", encoding="utf-8")
            salida = r.correr(Path("v.mp4"), archivo, Path(d), "X", "", "2026-10-28 10:00", "t", False, None)
        modelo.predecir.assert_called_once_with(mock.ANY, None, None)
        self.assertFalse([x for x in salida["licencia"]["no_pude_revisar"] if "V-JEPA" in x])

    def test_revisar_otra_vez_el_mismo_video_conserva_su_apertura(self):
        from retina import retina as r
        with tempfile.TemporaryDirectory() as d, mock.patch.object(r, "segmentar", return_value={"duracion_s": 60.0}), \
                mock.patch.object(r, "preparar_carpeta"), mock.patch.object(r, "solo_modelos_meta", return_value=True):
            (Path(d) / "apertura.json").write_text('{"aprobada": true}', encoding="utf-8")
            r.correr(Path("v.mp4"), None, Path(d), "X", "", "2026-10-28 10:00", "t", False, None)
            hecho = json.loads((Path(d) / "resultado.json").read_text(encoding="utf-8"))
        self.assertEqual(hecho["apertura"], {"aprobada": True})

    def test_con_la_formula_apagada_no_tener_numero_no_es_una_falta(self):
        from retina import retina as r
        with tempfile.TemporaryDirectory() as d, mock.patch.object(r, "segmentar", return_value={"duracion_s": 60.0}), \
                mock.patch.object(r, "preparar_carpeta"), mock.patch.object(r, "solo_modelos_meta", return_value=True):
            salida = r.correr(Path("v.mp4"), None, Path(d), "X", "", "2026-10-28 10:00", "t", False, None)
        self.assertIsNone(salida["prediccion"])
        self.assertFalse([x for x in salida["licencia"]["no_pude_revisar"] if x.startswith("El número")])

    def test_sin_nivel_la_tarjeta_no_esta_obligada_a_proponer_un_cambio(self):
        sin_cambio = tarjeta(que_cambiar="", pasos=[])
        con_alto = explicar.revisar(sin_cambio, {**DATOS, "nivel_de_riesgo": "alto"})
        self.assertIn("el nivel no es «bajo» y no trae un cambio", con_alto)
        self.assertNotIn("el nivel no es «bajo» y no trae un cambio",
                         explicar.revisar(sin_cambio, {**DATOS, "nivel_de_riesgo": "sin_nivel"}))


if __name__ == "__main__":
    unittest.main()
