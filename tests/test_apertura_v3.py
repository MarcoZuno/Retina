"""apertura-v3: una sola prueba, cifras reales, tres dibujos revisados y el inicio que ya funciona."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from retina import apertura, integridad, titulo

VOZ = ("Las pulgas de tu perro se esconden detrás de sus orejas, y por eso revisar ahí primero evita que la plaga crezca en casa "
       "durante las semanas de más calor en todo el año.")
CUADROS = ["Un perro grande al centro", "Una mano revisa una oreja", "Un cepillo sobre una mesa"]


def datos(**extra):
    return {"titulo": "Pulgas del perro en casa", "fuente": "pulgas perro orejas casa", "duracion_video_s": 120, **extra}


class Reglas(unittest.TestCase):
    def test_una_lista_no_pasa(self):
        for voz in ("Tu perro cojea, no come y tiembla.", "Primero, revisa sus orejas; segundo, sus patas.",
                    "Revisa orejas, patas, cola, lomo y panza."):
            self.assertTrue(apertura.enumera(voz), voz)

    def test_una_frase_normal_no_es_lista(self):
        self.assertFalse(apertura.enumera(VOZ))
        self.assertFalse(apertura.enumera("Cuando llegó a la clínica, la veterinaria vio algo que nadie esperaba en su pata."))
        self.assertFalse(apertura.enumera("Soy veterinaria, y esto es lo primero que reviso."))

    def test_cifras_pegadas_y_compuestas(self):
        self.assertEqual(apertura.cifras_nuevas("Pesa 100 kilos", "pesa 100kg"), [])
        self.assertEqual(apertura.cifras_nuevas("Se ve en 4K", "video 4k"), [])
        self.assertEqual(apertura.cifras_nuevas("Tiene 35 años", "tiene treinta y cinco años"), [])
        self.assertEqual(apertura.cifras_nuevas("It has 35 parts", "thirty-five parts"), [])

    def test_magnitudes_inventadas(self):
        self.assertIn("1000", apertura.cifras_nuevas("Lo vieron miles de personas", "lo vio una persona"))

    def test_cifra_en_cuadro(self):
        s = {"voz": VOZ, "cuadros": ["Un letrero dice 99 %", CUADROS[1], CUADROS[2]]}
        self.assertIn("cifras", [p["id"] for p in apertura.revisar(s, datos())])

    def test_palabra_de_cantidad_en_cuadro_no_cuenta(self):
        s = {"voz": VOZ, "cuadros": ["Dos perros al centro", CUADROS[1], CUADROS[2]]}
        self.assertNotIn("cifras", [p["id"] for p in apertura.revisar(s, datos())])

    def test_nombre_tras_dos_puntos(self):
        self.assertEqual(apertura.nombres_nuevos("Esto dijo: Ramírez ganó", "esto dijo gano"), ["Ramírez"])

    def test_enlaces(self):
        s = {"voz": VOZ + " Mira www.ejemplo.com", "cuadros": CUADROS}
        self.assertIn("anzuelos", [p["id"] for p in apertura.revisar(s, datos())])

    def test_video_corto(self):
        self.assertEqual(apertura.limites_de_voz({"duracion_video_s": 6}), (10, 15))
        self.assertEqual(apertura.limites_de_voz({"duracion_video_s": 120}), (25, 45))

    def test_video_mudo(self):
        self.assertEqual(apertura.limites_de_voz({"video_mudo": True, "duracion_video_s": 60}), (5, 16))


class Anzuelos(unittest.TestCase):
    def test_disfraces(self):
        for t in ("cοmenta", "c o m e n t a abajo", "Follow for more", "activa la campanita"):
            self.assertTrue(integridad.revisar(t), t)

    def test_palabras_normales(self):
        self.assertFalse(integridad.revisar("a b c son letras"))


class Lazo(unittest.TestCase):
    def correr(self, respuestas, comprobar=None, **extra):
        pedidos = iter(respuestas)
        dibujados = []

        def dibujar(i, c):
            dibujados.append(i)
            return Path(f"c{i}.png")

        r = apertura.lazo(datos(**extra), None, lambda d, a: next(pedidos), dibujar, lambda i, c: {}, comprobar=comprobar)
        return r, dibujados

    def test_dibujo_que_no_coincide_se_corrige(self):
        veces = []

        def comprobar(imagen, texto):
            veces.append(imagen.name)
            return len(veces) > 3

        r, dibujados = self.correr([{"voz": VOZ, "cuadros": CUADROS}] * 2, comprobar)
        self.assertTrue(r["aprobada"])
        self.assertEqual(r["vueltas"], 1)
        self.assertEqual(len(dibujados), 6)
        self.assertEqual([f["coincide"] for f in r["despues"]["cuadros_revisados"]], [True, True, True])

    def test_falla_de_revision_no_cuenta_como_buena_ni_se_aprueba(self):
        def comprobar(imagen, texto):
            raise RuntimeError

        r, dibujados = self.correr([{"voz": VOZ, "cuadros": CUADROS}], comprobar)
        self.assertFalse(r["aprobada"])
        self.assertTrue(r["incompleta"])
        self.assertIsNone(r["despues"])
        self.assertIn("cuadros", r["no_comprobe"])
        self.assertNotIn("cuadros", [c["id"] for c in r["comprobaciones"]])
        self.assertEqual((r["vueltas"], dibujados), (0, [1, 2, 3]))  # no se pide corregir: el texto no estaba mal

    def test_si_sam_no_contesta_se_deja_de_gastar_y_no_se_aprueba(self):
        def medir(imagen, c):
            raise RuntimeError("SAM no contestó")

        dibujados = []

        def dibujar(i, c):
            dibujados.append(i)
            return Path(f"c{i}.png")

        r = apertura.lazo(datos(), "dog", lambda _d, _a: {"voz": VOZ, "cuadros": CUADROS}, dibujar, medir)
        self.assertFalse(r["aprobada"])
        self.assertTrue(r["incompleta"])
        self.assertEqual((r["no_comprobe"], r["vueltas"], dibujados), (["promesa"], 0, [1]))  # los otros dos cuadros no se pagan
        self.assertEqual(r["intentos"][-1]["problemas"], [])

    def test_un_dibujo_que_falla_se_vuelve_a_pedir(self):
        dibujos = iter([RuntimeError(), Path("1"), Path("2"), Path("3")])

        def dibujar(i, c):
            d = next(dibujos)
            if isinstance(d, Exception):
                raise d
            return d

        r = apertura.lazo(datos(), "dog", lambda _d, _a: {"voz": VOZ, "cuadros": CUADROS}, dibujar,
                          lambda imagen, c: {"aparece": True, "primer_segundo": 0})
        self.assertTrue(r["aprobada"])
        self.assertEqual(r["vueltas"], 1)
        self.assertEqual(r["no_comprobe"], [])

    def test_inicio_que_ya_funciona(self):
        frases = [{"segundo": 0, "dice": "Pulgas del perro: se esconden detrás de las orejas y por eso conviene revisar ahí cada semana durante todo el año en casa."}]
        r, dibujados = self.correr([{"ya_funciona": True, "motivo": "Dice el tema de inmediato.", "voz": "", "cuadros": []}], frases=frases)
        self.assertTrue(r["aprobada"] and r["ya_funciona"])
        self.assertIsNone(r["despues"])
        self.assertEqual(dibujados, [])

    def test_el_codigo_no_le_cree_si_el_inicio_trae_anzuelo(self):
        frases = [{"segundo": 0, "dice": "Pulgas del perro en casa: comenta abajo si te pasó y te digo cómo revisar a tu perro hoy mismo sin gastar nada en todo el mes."}]
        r, _ = self.correr([{"ya_funciona": True, "motivo": "Sirve.", "voz": "", "cuadros": []}, {"voz": VOZ, "cuadros": CUADROS}], frases=frases)
        self.assertTrue(r["aprobada"])
        self.assertNotIn("ya_funciona", r)
        self.assertEqual(r["intentos"][0]["problemas"][0]["id"], "ya_funciona")

    def test_saludo_no_ya_funciona(self):
        frases = [{"segundo": 0, "dice": "Hola, pulgas del perro en casa: se esconden detrás de las orejas y conviene revisar ahí cada semana todo el año entero."}]
        self.assertIn("saludo", apertura.por_que_no_sirve(datos(frases=frases)))

    def test_tema_tardio_no_ya_funciona(self):
        frases = [{"segundo": 0, "dice": "Esto me pasó ayer cuando salí muy temprano de mi trabajo a la calle y entonces vi las pulgas del perro en casa todo el día."}]
        self.assertIn("tarda", apertura.por_que_no_sirve(datos(frases=frases)))

    def test_si_lo_prometido_no_se_ve_no_ya_funciona(self):
        frases = [{"segundo": 0, "dice": "Pulgas del perro en casa: se esconden detrás de las orejas y conviene revisar ahí cada semana durante todo el año entero."}]
        self.assertIn("no se ve", apertura.por_que_no_sirve(datos(frases=frases, promesa_en_el_inicio=False)))


class Titulo(unittest.TestCase):
    def test_sin_datos_no_opina(self):
        self.assertIsNone(titulo.revisar("", "algo", "")["cumple"])
        self.assertIsNone(titulo.revisar("Título", "", "")["cumple"])

    def test_filtro(self):
        self.assertTrue(titulo.aceptable({"cumple": "no", "por_que": "El video no habla de eso."}))
        self.assertFalse(titulo.aceptable({"cumple": "no", "por_que": "Comenta abajo."}))
        self.assertFalse(titulo.aceptable({"cumple": "no", "por_que": "Mira http://x.com"}))
        self.assertFalse(titulo.aceptable({"cumple": "tal vez", "por_que": "Quién sabe."}))


class Fidelidad(unittest.TestCase):
    """Lo que las reglas no ven: una apertura sin cifras ni nombres nuevos que agrega algo. Corre antes de dibujar."""

    def correr(self, veredictos, pedidos=None):
        dibujados, cola = [], iter(veredictos)
        pedidos = iter(pedidos or [{"voz": VOZ, "cuadros": CUADROS}] * 3)

        def dibujar(i, c):
            dibujados.append(i)
            return Path(f"c{i}.png")

        def fiel(voz, d):
            v = next(cola)
            if isinstance(v, Exception):
                raise v
            return v

        r = apertura.lazo(datos(), None, lambda d, a: next(pedidos), dibujar, lambda i, c: {}, comprobar=lambda i, c: True, fiel=fiel)
        return r, dibujados

    def test_lo_infiel_se_regresa_y_no_se_dibuja(self):
        r, dibujados = self.correr([{"fiel": False, "que_agrega": "el café de la mañana"}, {"fiel": True, "que_agrega": ""}])
        self.assertTrue(r["aprobada"])
        self.assertEqual(r["vueltas"], 1)
        self.assertEqual(r["intentos"][0]["problemas"][0]["id"], "fidelidad")
        self.assertIn("café", r["intentos"][0]["problemas"][0]["detalle"])
        self.assertEqual(dibujados, [1, 2, 3])

    def test_infiel_tres_veces_no_llega(self):
        r, dibujados = self.correr([{"fiel": False, "que_agrega": "algo"}] * 3)
        self.assertFalse(r["aprobada"])
        self.assertEqual(dibujados, [])

    def test_si_no_contesta_no_finge_que_paso_ni_se_dibuja(self):
        r, dibujados = self.correr([RuntimeError("sin respuesta")])
        self.assertFalse(r["aprobada"])
        self.assertTrue(r["incompleta"])
        self.assertIsNone(r["despues"])
        self.assertIn("fidelidad", r["no_comprobe"])
        self.assertNotIn("fidelidad", [c["id"] for c in r["comprobaciones"]])
        self.assertEqual(dibujados, [])  # sin lectura no se gasta en dibujar


class Saludo(unittest.TestCase):
    def test_saludos(self):
        for t in ("Good morning friends", "Hi guys", "Hey everyone", "Hola amigos", "Qué onda banda"):
            self.assertIn("saludo", [p["id"] for p in apertura.revisar({"voz": f"{t}. {VOZ}", "cuadros": CUADROS}, datos())], t)

    def test_sin_saludo(self):
        self.assertNotIn("saludo", [p["id"] for p in apertura.revisar({"voz": VOZ, "cuadros": CUADROS}, datos())])

    def test_palabra_parecida_no_es_saludo(self):
        self.assertIsNone(apertura.SALUDO.search("hipotesis de la cholita"))


class Tema(unittest.TestCase):
    def armar(self, carpeta, tema):
        (carpeta / "describir.json").write_text('{"tramos": []}', encoding="utf-8")
        with mock.patch.object(apertura, "datos_de_apertura", return_value=datos(frases=[], resto_de_lo_que_se_dice="algo", idioma_de_la_apertura="español")), \
                mock.patch.object(apertura, "tema_fuera", **tema), mock.patch.object(apertura, "lazo", return_value={
                    "aprobada": False, "vueltas": 0, "despues": None, "comprobaciones": [], "intentos": [], "no_comprobe": []}) as lazo:
            return apertura.armar(carpeta, "Título", None), lazo

    def test_salud_no_se_reescribe_ni_se_gasta(self):
        with tempfile.TemporaryDirectory() as t:
            r, lazo = self.armar(Path(t), {"return_value": "salud"})
        self.assertEqual(r["fuera_de_alcance"], "salud")
        self.assertFalse(r["aprobada"])
        lazo.assert_not_called()

    def test_si_no_contesta_se_dice_y_no_se_escribe(self):
        with tempfile.TemporaryDirectory() as t:
            r, lazo = self.armar(Path(t), {"side_effect": RuntimeError("sin respuesta")})
        lazo.assert_not_called()  # sin saber si el tema se puede reescribir, no se gasta ni se entrega nada
        self.assertFalse(r["aprobada"])
        self.assertTrue(r["incompleta"])
        self.assertIn("tema_sensible", r["no_comprobe"])


if __name__ == "__main__":
    unittest.main()
