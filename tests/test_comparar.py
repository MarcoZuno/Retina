"""Tests de «comparar» (dos versiones del mismo video) sin API: Spark se sustituye por un `pedir` falso.

Corren con:  python -m unittest discover -s tests   (desde la raíz del repo)
"""
from __future__ import annotations

import functools
import http.client
import http.server
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from retina import comparar, meta_api  # noqa: E402

ANZUELO = "Comparte este video para que más personas entiendan lo del pañuelo."


def caso(carpeta: Path, abre: str, voz_ms: int = 60) -> Path:
    """Una revisión ya terminada, mínima: 10 partes de 2.5 segundos, voz, Meta y su tarjeta."""
    carpeta.mkdir(parents=True)
    tramos = [{"tramo": i, "inicio_s": 2.5 * i, "fin_s": 2.5 * (i + 1)} for i in range(12)]
    (carpeta / "manifiesto.json").write_text(json.dumps({"duracion_s": 98.0, "tramos": tramos}), encoding="utf-8")
    desc = [{"tramo": i, "que_pasa": abre if i == 0 else "La presentadora explica.", "texto_en_pantalla": "",
             "tipo_de_plano": "plano_medio", "cambio_de_plano": False, "presentador_en_pantalla": True,
             "tipo_de_gancho": "pregunta" if i == 0 else "ninguno"} for i in range(12)]
    (carpeta / "describir.json").write_text(json.dumps({"tramos": desc}, ensure_ascii=False), encoding="utf-8")
    voz = {"arranque_voz_ms": voz_ms, "silencios": [{"inicio_ms": 4900, "fin_ms": 7400}],
           "turnos": [{"startMs": voz_ms, "transcript": "Imagínate ser un niño y que el ruido te haga taparte los oídos."},
                      {"startMs": 9000, "transcript": ANZUELO}]}
    (carpeta / "transcribir.json").write_text(json.dumps(voz, ensure_ascii=False), encoding="utf-8")
    resultado = {"arranque": {"nivel": "bajo", "bloques": [{"caida_parecidos_pp": 66.2}, {"caida_parecidos_pp": 13.7}]},
                 "explicacion": {"por_que": "En el segundo 0 se ve al niño con el pañuelo.", "lo_que_funciona": "",
                                 "que_cambiar": f"Quita «{ANZUELO}»", "anzuelo_detectado": "pide_interaccion",
                                 "anzuelo_frase": ANZUELO, "licencia": {"traza": ["no va al modelo"]}},
                 "revision_meta": [{"id": "gancho_3s", "regla": "Algo que detenga a la gente en los primeros 3 segundos",
                                    "cumple": True, "evidencia": "En el segundo 0 abre con una pregunta.",
                                    "fuente": "https://www.facebook.com/business/help/1675722002698686"}]}
    (carpeta / "resultado.json").write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")
    return carpeta


def juicio(mejor="primera", **cambios) -> dict:
    j = {"mejor": mejor, "por_que": "La versión 1 abre con la pregunta en el segundo 0 y la versión 2 tarda más.",
         "diferencias": [
             {"aspecto": "Gancho", "primera": "Abre con la pregunta en el segundo 0.",
              "segunda": "Abre con la presentación.", "mejor": "primera" if mejor == "primera" else "segunda"},
             {"aspecto": "Silencios", "primera": "Silencio del segundo 4.9 al 7.4.",
              "segunda": "El mismo silencio.", "mejor": "igual"}]}
    j.update(cambios)
    return j


def datos_falsos() -> dict:
    with tempfile.TemporaryDirectory() as d:
        a, b = caso(Path(d) / "a", "Abre con la pregunta."), caso(Path(d) / "b", "Abre con la presentación.")
        return {"version_1": comparar.datos_de_version(a), "version_2": comparar.datos_de_version(b)}


class DatosDeCadaVersion(unittest.TestCase):
    def test_lleva_lo_que_se_ve_y_se_oye_pero_no_las_cifras_de_retencion(self):
        with tempfile.TemporaryDirectory() as d:
            v = comparar.datos_de_version(caso(Path(d) / "a", "Abre con la pregunta."))
        self.assertEqual(v["tramos"][0]["que_pasa"], "Abre con la pregunta.")
        self.assertEqual((v["voz_arranca_s"], v["silencios_s"], v["duracion_video_s"]), (0.1, [[4.9, 7.4]], 98.0))
        self.assertNotIn("caida_de_videos_parecidos_pp", v)  # salen de los metadatos: casi iguales en dos versiones
        self.assertNotIn("nivel_de_riesgo", v)
        self.assertEqual(v["revision_meta"][0], {"regla": "Algo que detenga a la gente en los primeros 3 segundos",
                                                 "cumple": True, "evidencia": "En el segundo 0 abre con una pregunta."})
        self.assertEqual(v["tarjeta"]["lo_bueno"], [])  # una tarjeta vieja sin los campos nuevos no truena
        self.assertEqual(v["tarjeta"]["anzuelo_frase"], ANZUELO)
        self.assertNotIn("licencia", v["tarjeta"])

    def test_solo_van_las_revisiones_de_meta_que_se_hicieron_en_las_dos(self):
        # Smoke del 29-oct: el mismo video revisado dos veces; solo una corrida tenía SAM («lo que promete el
        # título») y Spark prefirió la otra en los dos órdenes. Eso no es algo que el editor cambió.
        llamadas = []

        def pedir(datos, aviso, motor):
            llamadas.append([[r["regla"] for r in datos[k]["revision_meta"]] for k in ("version_1", "version_2")])
            return juicio("empate")
        with tempfile.TemporaryDirectory() as d:
            a, b = caso(Path(d) / "a", "Abre con la pregunta."), caso(Path(d) / "b", "Abre con la presentación.")
            r = json.loads((b / "resultado.json").read_text(encoding="utf-8"))
            r["revision_meta"].append({"id": "promesa_3s", "regla": "Lo prometido se ve pronto", "cumple": False,
                                       "evidencia": "No se ve en los primeros 3 segundos."})
            (b / "resultado.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
            comparar.comparar(a, b, "abierto", pedir=pedir)
        regla = "Algo que detenga a la gente en los primeros 3 segundos"
        self.assertEqual(llamadas, [[[regla], [regla]], [[regla], [regla]]])


class Validador(unittest.TestCase):
    def setUp(self):
        self.datos = datos_falsos()

    def problemas(self, **cambios):
        return comparar.revisar(juicio(**cambios), self.datos)

    def test_un_juicio_bueno_pasa(self):
        self.assertEqual(self.problemas(), [])
        self.assertEqual(comparar.revisar(juicio("empate"), self.datos), [])

    def test_valores_que_no_existen(self):
        self.assertTrue(self.problemas(mejor="A"))
        malo = juicio()
        malo["diferencias"][0]["mejor"] = "las dos"
        self.assertTrue(comparar.revisar(malo, self.datos))
        self.assertTrue(comparar.revisar("no es un objeto", self.datos))
        self.assertTrue(comparar.revisar({"mejor": "primera"}, self.datos))

    def test_de_2_a_6_diferencias(self):
        d = juicio()["diferencias"]
        self.assertTrue(self.problemas(diferencias=d[:1]))
        self.assertTrue(self.problemas(diferencias=(d * 4)[:7]))
        self.assertEqual(self.problemas(diferencias=(d * 3)), [])

    def test_textos_largos(self):
        self.assertTrue(self.problemas(por_que="a" * 221))
        malo = juicio()
        malo["diferencias"][0]["aspecto"] = "a" * 61
        self.assertTrue(comparar.revisar(malo, self.datos))
        malo = juicio()
        malo["diferencias"][1]["segunda"] = "a" * 141
        self.assertTrue(comparar.revisar(malo, self.datos))

    def test_sin_jerga_ni_porcentajes(self):
        for texto in ("En el tramo 2 la versión 1 pierde menos.", "La versión 1 retiene 30 % más.",
                      "La versión 1 tiene texto_en_pantalla.", "En s4 la versión 2 se calla."):
            with self.subTest(texto=texto):
                self.assertTrue(any("jerga" in p for p in self.problemas(por_que=texto)))
        malo = juicio()
        malo["diferencias"][0]["aspecto"] = "tipo_de_gancho"
        self.assertTrue(any("jerga" in p for p in comparar.revisar(malo, self.datos)))

    def test_cifras_que_no_vienen_en_los_datos(self):
        p = self.problemas(por_que="La versión 1 abre en el segundo 47 y la versión 2 en el 0.")
        self.assertTrue(any("cifras" in x and "47" in x for x in p), p)
        self.assertEqual(self.problemas(por_que="La versión 1 calla del segundo 4.9 al 7.4; la versión 2 también."), [])

    def test_nunca_un_anzuelo_salvo_citado_tal_como_lo_dice_el_video(self):
        self.assertTrue(self.problemas(por_que="La versión 2 pide que comenten y eso engancha más."))
        self.assertEqual(self.problemas(por_que=f"Las dos cierran con «{ANZUELO}» en el segundo 9."), [])

    def test_si_elige_una_alguna_diferencia_la_favorece(self):
        sin_apoyo = juicio()
        sin_apoyo["diferencias"][0]["mejor"] = "igual"
        self.assertTrue(comparar.revisar(sin_apoyo, self.datos))


def pedir_falso(elige, llamadas=None):
    """Spark falso: `elige(primera, segunda)` dice qué versión elige según cuál llegó primero ('A' o 'B')."""
    def pedir(datos, aviso, motor):
        primera = "A" if datos["version_1"]["tramos"][0]["que_pasa"] == "Abre con la pregunta." else "B"
        segunda = "B" if primera == "A" else "A"
        if llamadas is not None:
            llamadas.append((primera, motor, aviso))
        gana = elige(primera, segunda)
        mejor = "empate" if gana == "empate" else ("primera" if gana == primera else "segunda")
        j = juicio(mejor)
        j["diferencias"][0].update(primera=f"Lo que hace la {primera}.", segunda=f"Lo que hace la {segunda}.")
        return j
    return pedir


class DosOrdenes(unittest.TestCase):
    def comparar(self, pedir, motor="abierto+api"):
        with tempfile.TemporaryDirectory() as d:
            a, b = caso(Path(d) / "a1b2c3d4e5f6", "Abre con la pregunta."), caso(Path(d) / "0f9e8d7c6b5a", "Abre con la presentación.")
            salida = comparar.comparar(a, b, motor, pedir=pedir)
            escrito = json.loads((b / "comparacion.json").read_text(encoding="utf-8"))
        self.assertEqual(salida, escrito)
        return salida

    def test_si_los_dos_ordenes_eligen_la_misma_esa_gana(self):
        llamadas = []
        s = self.comparar(pedir_falso(lambda p, s: "A", llamadas))
        self.assertEqual(list(s), ["version", "a", "b", "veredicto", "por_que", "diferencias", "juicios", "aviso", "licencia"])
        self.assertEqual((s["version"], s["a"], s["b"], s["veredicto"]), ("comparacion-v1", "a1b2c3d4e5f6", "0f9e8d7c6b5a", "A"))
        self.assertEqual([(x[0], x[1]) for x in llamadas], [("A", "abierto"), ("B", "abierto")])  # A/B y luego B/A
        self.assertEqual(s["juicios"], [
            {"orden": "AB", "mejor": "A", "por_que": "La versión A abre con la pregunta en el segundo 0 y la versión B tarda más."},
            {"orden": "BA", "mejor": "A", "por_que": "La versión B abre con la pregunta en el segundo 0 y la versión A tarda más."}])
        self.assertEqual(s["por_que"], s["juicios"][0]["por_que"])
        self.assertEqual(s["diferencias"][0], {"aspecto": "Gancho", "a": "Lo que hace la A.", "b": "Lo que hace la B.", "mejor": "A"})
        self.assertEqual(s["diferencias"][1]["mejor"], "igual")
        self.assertEqual(s["aviso"], "Es la opinión de Spark viendo cómo arranca cada versión, no una predicción de retención medida.")
        self.assertEqual(s["licencia"]["instrucciones"], "skills/comparar.md (comparar-v2)")
        self.assertEqual(s["licencia"]["servido_por"], "Baseten")
        self.assertEqual([i["orden"] for i in s["licencia"]["intentos"]], ["AB", "BA"])

    def test_si_siempre_elige_la_segunda_es_empate(self):
        # El sesgo que se midió en el juez por pares: con un solo orden eligió el segundo 10 de 10 veces.
        s = self.comparar(pedir_falso(lambda p, s: s))
        self.assertEqual(s["veredicto"], "empate")
        self.assertEqual([j["mejor"] for j in s["juicios"]], ["B", "A"])
        self.assertIn("no coincidieron", s["por_que"])
        self.assertEqual([d["mejor"] for d in s["diferencias"]], ["igual", "igual"])  # el gancho cambió de lado: no cuenta
        self.assertEqual(s["diferencias"][0]["a"], "Lo que hace la A.")

    def test_una_ganadora_sin_ninguna_diferencia_que_se_sostenga_es_empate(self):
        # Smoke del 29-oct (mismo video): las dos lecturas eligieron la B, pero cada aspecto cambió de lado.
        def pedir(datos, aviso, motor):
            primera = "A" if datos["version_1"]["tramos"][0]["que_pasa"] == "Abre con la pregunta." else "B"
            j = juicio("primera" if primera == "A" else "segunda")  # las dos veces elige la A...
            j["diferencias"][0]["mejor"] = "primera"  # ...pero el gancho favorece a la que llegó primero
            j["diferencias"][1]["mejor"] = "igual" if primera == "A" else "segunda"
            return j
        s = self.comparar(pedir)
        self.assertEqual([j["mejor"] for j in s["juicios"]], ["A", "A"])
        self.assertEqual([d["mejor"] for d in s["diferencias"]], ["igual", "igual"])
        self.assertEqual(s["veredicto"], "empate")
        self.assertIn("versión A", s["por_que"])
        self.assertIn("ninguna diferencia", s["por_que"])

    def test_un_empate_en_los_dos_ordenes_es_empate(self):
        s = self.comparar(pedir_falso(lambda p, s: "empate"))
        self.assertEqual((s["veredicto"], s["por_que"]), ("empate", s["juicios"][0]["por_que"]))

    def test_lo_rechazado_se_pide_otra_vez_con_el_aviso_y_luego_rescata_spark_13(self):
        avisos = []

        def pedir(datos, aviso, motor):
            avisos.append((motor, aviso))
            return juicio(por_que="a" * 300) if motor == "abierto" else juicio()
        s = self.comparar(pedir)
        self.assertEqual([m for m, _ in avisos], ["abierto", "abierto", "api"] * 2)
        self.assertEqual(avisos[0][1], "")
        self.assertIn("caracteres", avisos[1][1])
        self.assertEqual(s["licencia"]["servido_por"], "Meta Model API")
        self.assertEqual([i["motor"] for i in s["licencia"]["intentos"]], ["abierto", "abierto", "api"] * 2)

    def test_si_ningun_motor_pasa_el_validador_no_hay_comparacion(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = caso(Path(d) / "a", "Abre con la pregunta."), caso(Path(d) / "b", "Abre con la presentación.")
            with self.assertRaises(RuntimeError):
                comparar.comparar(a, b, "abierto+api", pedir=lambda datos, aviso, motor: juicio(mejor="A"))
            self.assertFalse((b / "comparacion.json").exists())

    def test_el_tope_de_gasto_detiene_todo_sin_reintentar(self):
        llamadas = []

        def pedir(datos, aviso, motor):
            llamadas.append(motor)
            raise meta_api.TopeAlcanzado("Tope del proyecto")
        with tempfile.TemporaryDirectory() as d:
            a, b = caso(Path(d) / "a", "Abre con la pregunta."), caso(Path(d) / "b", "Abre con la presentación.")
            with self.assertRaises(meta_api.TopeAlcanzado):
                comparar.comparar(a, b, "abierto+api", pedir=pedir)
        self.assertEqual(llamadas, ["abierto"])


class CabeceraDeLaVersionA(unittest.TestCase):
    def test_solo_una_revision_subida_a_este_servidor(self):
        from retina.app import comparar_con
        with tempfile.TemporaryDirectory() as d:
            casos = Path(d)
            (casos / "a1b2c3d4e5f6").mkdir()
            (casos / "a1b2c3d4e5f6" / "video.mp4").write_bytes(b"x")
            (casos / "0000aaaabbbb").mkdir()  # carpeta sin video: no es una subida
            self.assertIsNone(comparar_con({}, casos))
            self.assertIsNone(comparar_con({"X-Retina-Comparar-Con": ""}, casos))
            self.assertEqual(comparar_con({"X-Retina-Comparar-Con": "a1b2c3d4e5f6"}, casos), casos / "a1b2c3d4e5f6")
            for malo in ("../a1b2c3d4", "A1B2C3D4E5F6", "a1b2c3d4e5f", "a1b2c3d4e5f6a", "a1b2c3d4e5f6\n",
                         "ffffffffffff", "0000aaaabbbb", "..%2fx"):
                with self.subTest(malo=malo), self.assertRaises(ValueError):
                    comparar_con({"X-Retina-Comparar-Con": malo}, casos)


class SubirLaVersionB(unittest.TestCase):
    """POST /api/revisar con la cabecera: 400 si la versión A no sirve; si sirve, queda la marca antes de la fila."""

    def setUp(self):
        from retina.app import ConSubida
        self.dir = tempfile.TemporaryDirectory()
        self.casos = Path(self.dir.name)
        (self.casos / "a1b2c3d4e5f6").mkdir()
        (self.casos / "a1b2c3d4e5f6" / "video.mp4").write_bytes(b"x")
        self.enviados = []
        prueba = self

        class Fila:
            def submit(self, funcion, carpeta, *args):
                prueba.enviados.append((carpeta, (carpeta / "comparar_con.txt").exists()))
        clase = type("Manejador", (ConSubida,), {"casos": self.casos, "fila": Fila(), "modelos": {},
                                                  "log_message": lambda *a: None})
        self.servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(clase, directory=str(RAIZ)))
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        # Un equipo con ffmpeg y llave; la prueba de abajo quita la llave.
        self.salud = mock.patch("retina.app.salud", return_value={"ffmpeg": True, "llave": True})
        self.salud.start()

    def tearDown(self):
        self.salud.stop()
        self.servidor.shutdown()
        self.servidor.server_close()
        self.dir.cleanup()

    def subir(self, comparar_con: str | None, idioma: str = "es"):
        h = {"X-Retina": "1", "X-Retina-Titulo": "Prueba", "X-Retina-Fecha": "2026-10-29 10:00", "X-Retina-Publicado": "1",
             "Content-Type": "video/mp4", "X-Retina-Idioma": idioma}
        if comparar_con is not None:
            h["X-Retina-Comparar-Con"] = comparar_con
        c = http.client.HTTPConnection("127.0.0.1", self.servidor.server_port, timeout=10)
        c.request("POST", "/api/revisar", body=b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 20, headers=h)
        r = c.getresponse()
        cuerpo = json.loads(r.read().decode("utf-8"))
        c.close()
        return r.status, cuerpo

    def test_una_version_a_que_no_existe_es_400_y_no_se_guarda_nada(self):
        status, cuerpo = self.subir("ffffffffffff")
        self.assertEqual(status, 400)
        self.assertIn("versión A", cuerpo["error"])
        self.assertEqual(sorted(p.name for p in self.casos.iterdir()), ["a1b2c3d4e5f6"])
        self.assertEqual(self.enviados, [])

    def test_con_la_version_a_queda_la_marca_antes_de_entrar_a_la_fila(self):
        status, cuerpo = self.subir("a1b2c3d4e5f6")
        self.assertEqual(status, 202)
        carpeta = self.casos / cuerpo["id"]
        self.assertEqual((carpeta / "comparar_con.txt").read_text(encoding="utf-8"), "a1b2c3d4e5f6")
        self.assertEqual(self.enviados, [(carpeta, True)])

    def test_sin_la_cabecera_es_una_revision_de_siempre(self):
        status, cuerpo = self.subir(None)
        self.assertEqual(status, 202)
        self.assertFalse((self.casos / cuerpo["id"] / "comparar_con.txt").exists())

    def test_sin_llave_se_dice_antes_de_subir_y_en_el_idioma_del_panel(self):
        with mock.patch("retina.app.salud", return_value={"ffmpeg": True, "llave": False}):
            status, cuerpo = self.subir(None, idioma="en")
        self.assertEqual(status, 503)
        self.assertIn("MODEL_API_KEY", cuerpo["error"])
        self.assertIn("key is missing", cuerpo["error"])
        self.assertEqual(sorted(p.name for p in self.casos.iterdir()), ["a1b2c3d4e5f6"])  # no se guardó nada


class AvanceYRevision(unittest.TestCase):
    def test_el_paso_comparando_solo_aparece_con_la_marca(self):
        from retina.app import estado
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "estado.json").write_text('{"estado": "procesando"}', encoding="utf-8")
            for archivo in ("manifiesto.json", "transcribir.json", "describir.json", "agente.json"):
                (d / archivo).write_text("{}", encoding="utf-8")
            self.assertEqual(estado(d)["paso"], "terminando")  # una sola versión: los pasos de siempre
            (d / "comparar_con.txt").write_text("a1b2c3d4e5f6", encoding="utf-8")
            self.assertEqual(estado(d)["paso"], "comparando")
            (d / "comparacion.json").write_text("{}", encoding="utf-8")
            self.assertEqual(estado(d)["paso"], "terminando")
            (d / "agente.json").unlink()
            self.assertEqual(estado(d)["paso"], "escribiendo")

    def revisar_b(self, estado_a: dict | None, falla: Exception | None = None, marca: bool = True):
        from retina import app
        with tempfile.TemporaryDirectory() as d:
            casos = Path(d)
            a, b = casos / "a1b2c3d4e5f6", casos / "0f9e8d7c6b5a"
            a.mkdir(), b.mkdir()
            if estado_a is not None:
                (a / "estado.json").write_text(json.dumps(estado_a, ensure_ascii=False), encoding="utf-8")
            if marca:
                (b / "comparar_con.txt").write_text(a.name, encoding="utf-8")
            datos = {"codigo": "", "talento": "", "fecha": "2026-10-29 10:00", "titulo": "Prueba", "publicado": True}
            modelos = {"modelo": None, "arranque": None, "voz": None}
            with mock.patch("retina.retina.correr") as correr, \
                    mock.patch("retina.comparar.comparar", side_effect=falla) as comparar_:
                app.revisar(b, datos, modelos, espera_s=0.2)
            correr.assert_called_once()
            return json.loads((b / "estado.json").read_text(encoding="utf-8")), comparar_

    def test_con_la_version_a_lista_se_compara_y_luego_queda_lista(self):
        e, comparar_ = self.revisar_b({"estado": "listo"})
        self.assertEqual(e, {"estado": "listo"})
        a, b = comparar_.call_args.args
        self.assertEqual((a.name, b.name), ("a1b2c3d4e5f6", "0f9e8d7c6b5a"))

    def test_sin_marca_no_se_compara(self):
        e, comparar_ = self.revisar_b(None, marca=False)
        self.assertEqual(e, {"estado": "listo"})
        comparar_.assert_not_called()

    def test_si_la_version_a_fallo_la_b_sale_con_error(self):
        e, comparar_ = self.revisar_b({"estado": "error", "mensaje": "El candado está encendido."})
        self.assertEqual(e["estado"], "error")
        self.assertIn("versión A", e["mensaje"])
        comparar_.assert_not_called()

    def test_si_la_comparacion_falla_la_tarjeta_de_b_se_queda(self):
        e, _ = self.revisar_b({"estado": "listo"}, falla=RuntimeError("sin JSON"))
        self.assertEqual(e["estado"], "listo")
        self.assertIn("comparar", e["comparacion_error"])

    def test_si_la_version_a_no_termina_a_tiempo_b_queda_lista_y_lo_dice(self):
        e, comparar_ = self.revisar_b({"estado": "procesando"})
        self.assertEqual(e["estado"], "listo")
        self.assertIn("versión A", e["comparacion_error"])
        comparar_.assert_not_called()


class ElPanelLeeLaComparacion(unittest.TestCase):
    def test_se_sirve_comparacion_json_de_un_caso_y_nada_mas(self):
        from retina.demo import PERMITIDO, ruta_local
        self.assertTrue(PERMITIDO.match("/casos/0f9e8d7c6b5a/comparacion.json"))
        privada = Path("D:/privado/casos")
        self.assertEqual(ruta_local("/casos/0f9e8d7c6b5a/comparacion.json", RAIZ, privada),
                         privada / "0f9e8d7c6b5a" / "comparacion.json")
        for ruta in ("/casos/../comparacion.json", "/casos/x/../comparacion.json", "/casos/comparacion.json",
                     "/casos/x/sub/comparacion.json", "/casos/x/comparacion.json.bak", "/casos/%2e%2e/comparacion.json",
                     "/casos/x/comparar_con.txt", "/casos/x/estado.json"):
            with self.subTest(ruta=ruta):
                self.assertFalse(PERMITIDO.match(ruta), ruta)


if __name__ == "__main__":
    unittest.main()
