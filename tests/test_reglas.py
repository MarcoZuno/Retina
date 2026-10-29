"""Tests sin API ni datos privados: filtros, validador, SAM, tope y formato del panel.

Corren con:  python -m unittest discover -s tests   (desde la raíz del repo)
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

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


def tarjeta(**cambios) -> dict:
    t = dict(por_que="Del segundo 0.6 al 4.9 no se ve la pila de tortillas.", lo_que_funciona="",
             que_cambiar="Mueve el plano de la pila al segundo 0.", pasos=["Corta el plano de la pila y ponlo al inicio."],
             tipo_de_cambio="reordenar", momento_s=0.0,
             anzuelo_detectado="ninguno", anzuelo_frase="", anzuelo_momento_s=-1, confianza="media",
             storyboard=[], no_pude_verificar=[])
    t.update(cambios)
    return t


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
        with mock.patch("openai.OpenAI", Cliente), mock.patch.object(baseten, "_llave", return_value="x"), \
                mock.patch.object(meta_api, "_registrar"):
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
    def test_el_env_no_sube_el_tope_autorizado(self):
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
        self.assertIn(r["arranque"]["nivel"], ("alto", "medio", "bajo"))
        self.assertEqual(len(r["prediccion"]["curva_predicha"]), 41)
        self.assertEqual(len(r["prediccion"]["curva_parecidos"]), 41)
        for campo in explicar.esquema()["required"]:
            self.assertIn(campo, r["explicacion"])
        for campo in ("comparado_con", "datos_hasta", "no_pude_revisar"):
            self.assertIn(campo, r["licencia"])

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

    def test_la_galeria_y_su_indice_se_sirven(self):
        from retina.demo import PERMITIDO
        for ruta in ("/panel/galeria.html", "/panel/subir.html", "/casos/indice.json"):
            self.assertTrue(PERMITIDO.match(ruta), ruta)
        for ruta in ("/casos/otro.json", "/panel/galeria.js", "/casos/x/indice.json"):
            self.assertFalse(PERMITIDO.match(ruta), ruta)

    def test_con_una_carpeta_privada_los_casos_salen_de_ahi_y_de_nada_mas(self):
        from retina.demo import ruta_local
        privada = Path("D:/privado/casos")
        self.assertEqual(ruta_local("/casos/ABC1/resultado.json", RAIZ, privada), privada / "ABC1" / "resultado.json")
        self.assertEqual(ruta_local("/casos/indice.json", RAIZ, privada), privada / "indice.json")
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

    def test_el_candado_viene_encendido_y_se_apaga_con_cero(self):
        from retina.retina import solo_publicados
        os.environ.pop("RETINA_SOLO_PUBLICADOS", None)
        self.assertTrue(solo_publicados() or os.environ.get("RETINA_SOLO_PUBLICADOS") == "0")
        os.environ["RETINA_SOLO_PUBLICADOS"] = "0"
        self.assertFalse(solo_publicados())


if __name__ == "__main__":
    unittest.main()
