"""Cambiar de idioma: lo que escribió el modelo también se traduce, sin agregar nada y sin pagarse dos veces.

Sin API, sin llaves y sin red. Corren con:  python -m unittest discover -s tests   (desde la raíz del repo)
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

from retina import app, meta_api, traducir  # noqa: E402

CASO = {"idioma": "en", "video": {"titulo": "Pan dulce"},
        "explicacion": {"por_que": "From second 4 the voice repeats.", "lo_bueno": ["Good close-up at second 1."], "pasos": ["Cut 2 seconds."],
                        "que_cambiar": "", "lo_flojo": [], "confianza": "media"},
        "normas": {"hallazgos": [{"norma": "bienes_restringidos", "nombre": "x", "por_que": "It could break a rule.", "evidencia": "te lo mando hoy mismo"}]},
        "revision_meta": [{"id": "gancho_3s", "evidencia": "At second 0 it opens with a fact."}],
        "apertura": {"despues": {"voz": "Tu pan dulce no se endurece."}}}
BIEN = ["Desde el segundo 4 la voz repite.", "Buen acercamiento en el segundo 1.", "Corta 2 segundos.", "Podría romper una regla.", "En el segundo 0 abre con un dato."]


class Traducir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)
        (self.d / "resultado.json").write_text(json.dumps(CASO), encoding="utf-8")

    def test_traduce_lo_que_escribio_el_modelo_y_el_original_no_se_toca(self):
        with mock.patch.object(traducir, "pedir", return_value=BIEN) as pedir:
            r = traducir.traducir(self.d, "es")
        self.assertEqual(pedir.call_args.args[0][0], "From second 4 the voice repeats.")
        self.assertEqual(r["explicacion"]["por_que"], BIEN[0])
        self.assertEqual(r["explicacion"]["pasos"], ["Corta 2 segundos."])
        self.assertEqual(r["revision_meta"][0]["evidencia"], BIEN[4])
        self.assertEqual(r["idioma"], "es")
        self.assertEqual(json.loads((self.d / "resultado.json").read_text(encoding="utf-8"))["idioma"], "en")

    def test_lo_que_sale_del_video_no_se_traduce(self):
        with mock.patch.object(traducir, "pedir", return_value=BIEN) as pedir:
            r = traducir.traducir(self.d, "es")
        self.assertEqual(r["apertura"]["despues"]["voz"], "Tu pan dulce no se endurece.")
        self.assertEqual(r["normas"]["hallazgos"][0]["evidencia"], "te lo mando hoy mismo")
        self.assertNotIn("te lo mando hoy mismo", pedir.call_args.args[0])

    def test_el_nombre_de_la_norma_sale_de_la_lista_oficial(self):
        with mock.patch.object(traducir, "pedir", return_value=BIEN):
            r = traducir.traducir(self.d, "es")
        nombre = {n["id"]: n["nombre"] for n in traducir.normas.reglas()}["bienes_restringidos"]
        self.assertEqual(r["normas"]["hallazgos"][0]["nombre"], nombre)

    def test_no_se_paga_dos_veces(self):
        with mock.patch.object(traducir, "pedir", return_value=BIEN) as pedir:
            traducir.traducir(self.d, "es")
            traducir.traducir(self.d, "es")
        pedir.assert_called_once()

    def test_en_su_propio_idioma_no_se_gasta(self):
        with mock.patch.object(traducir, "pedir", side_effect=AssertionError("gastó")):
            self.assertEqual(traducir.traducir(self.d, "en")["explicacion"]["por_que"], CASO["explicacion"]["por_que"])

    def test_una_cifra_cambiada_deja_el_texto_como_estaba(self):
        malo = ["Desde el segundo 9 la voz repite.", *BIEN[1:]]
        with mock.patch.object(traducir, "pedir", return_value=malo):
            r = traducir.traducir(self.d, "es")
        self.assertEqual(r["explicacion"]["por_que"], CASO["explicacion"]["por_que"])
        self.assertEqual(r["explicacion"]["pasos"], ["Corta 2 segundos."])

    def test_una_traduccion_no_puede_meter_un_anzuelo(self):
        self.assertFalse(traducir.aceptable("Cut 2 seconds.", "Corta 2 segundos y comenta abajo."))
        self.assertTrue(traducir.aceptable("Cut 2 seconds.", "Corta 2 segundos."))

    def test_si_faltan_textos_avisa_y_no_guarda_nada(self):
        with mock.patch.object(traducir, "pedir", return_value=BIEN[:2]), self.assertRaises(RuntimeError):
            traducir.traducir(self.d, "es")
        self.assertFalse((self.d / "resultado-es.json").exists())

    def test_desde_la_app_sin_llave_se_avisa_sin_gastar(self):
        with mock.patch.object(app, "salud", return_value={"ffmpeg": True, "llave": False}), mock.patch.object(traducir, "pedir", side_effect=AssertionError("gastó")):
            codigo, cuerpo = app.pedir_traduccion(self.d, "es")
        self.assertEqual(codigo, 503)
        self.assertTrue(cuerpo["error"])

    def test_desde_la_app_regresa_la_revision_traducida(self):
        with mock.patch.object(app, "salud", return_value={"ffmpeg": True, "llave": True}), mock.patch.object(traducir, "pedir", return_value=BIEN):
            codigo, cuerpo = app.pedir_traduccion(self.d, "es")
        self.assertEqual((codigo, cuerpo["idioma"]), (200, "es"))

    def test_el_tope_se_explica(self):
        with mock.patch.object(app, "salud", return_value={"ffmpeg": True, "llave": True}), mock.patch.object(traducir, "pedir", side_effect=meta_api.TopeAlcanzado("tope")):
            codigo, cuerpo = app.pedir_traduccion(self.d, "es")
        self.assertEqual(codigo, 503)
        self.assertIn("tope", cuerpo["error"].lower())

    def test_sin_revision_no_hay_nada_que_traducir(self):
        self.assertEqual(app.pedir_traduccion(self.d / "no-existe", "es")[0], 404)


if __name__ == "__main__":
    unittest.main()
