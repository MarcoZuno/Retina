"""La revisión de normas de Facebook: lista cerrada, evidencia real y nada de lo que el modelo no pueda sostener.

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

from retina import meta_api, normas  # noqa: E402

DATOS = {"titulo": "Compra este vape barato", "duracion_video_s": 60.0,
         "se_ve": [{"segundo": 0, "que_pasa": "Una mano sostiene un vapeador sobre la mesa.", "texto_en_pantalla": "Oferta de hoy"}],
         "se_dice": [{"segundo": 12, "dice": "Escribe a este número y te lo mando hoy mismo"}]}


def hallazgo(**cambios) -> dict:
    return {"norma": "bienes_restringidos", "segundo": 12, "evidencia": "te lo mando hoy mismo",
            "por_que": "Podría ser venta de un producto restringido.", **cambios}


def respuesta(hallazgos: list[dict]) -> dict:
    texto = json.dumps({"hallazgos": hallazgos})
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": texto}]}]}


class ListaDeNormas(unittest.TestCase):
    def test_cada_norma_trae_nombre_en_los_dos_idiomas_y_fuente_de_meta(self):
        lista = normas.reglas()
        self.assertGreaterEqual(len(lista), 15)
        for n in lista:
            with self.subTest(norma=n["id"]):
                self.assertTrue(n["nombre"] and n["name"] and n["que_buscar"])
                self.assertRegex(n["fuente"], r"^https://(transparency\.meta\.com|www\.facebook\.com)/")


class SoloLoQueSeSostiene(unittest.TestCase):
    def test_un_hallazgo_con_evidencia_real_pasa(self):
        self.assertEqual(len(normas.filtrar([hallazgo()], DATOS)), 1)

    def test_la_evidencia_se_compara_sin_acentos_ni_mayusculas(self):
        self.assertEqual(len(normas.filtrar([hallazgo(evidencia="TE LO MANDÓ HOY MISMO")], DATOS)), 1)

    def test_una_evidencia_inventada_se_descarta(self):
        self.assertEqual(normas.filtrar([hallazgo(evidencia="fuma diario y no pasa nada")], DATOS), [])

    def test_una_evidencia_de_una_o_dos_palabras_no_sostiene_nada(self):
        self.assertEqual(normas.filtrar([hallazgo(evidencia="hoy mismo")], DATOS), [])

    def test_la_cita_tiene_que_estar_en_ese_segundo(self):
        self.assertEqual(normas.filtrar([hallazgo(segundo=40)], {**DATOS, "se_dice": [*DATOS["se_dice"], {"segundo": 30, "dice": "ya otra cosa"}]}), [])

    def test_un_turno_largo_cuenta_hasta_que_empieza_el_siguiente(self):
        self.assertEqual(len(normas.filtrar([hallazgo(segundo=25)], DATOS)), 1)

    def test_la_cita_no_puede_salir_de_los_nombres_de_los_campos(self):
        self.assertEqual(normas.filtrar([hallazgo(evidencia="segundo 12 dice")], DATOS), [])

    def test_la_cita_no_puede_juntar_dos_momentos(self):
        self.assertEqual(normas.filtrar([hallazgo(segundo=0, evidencia="sobre la mesa Oferta de hoy")], DATOS), [])

    def test_la_cita_del_titulo_vale_en_cualquier_segundo(self):
        self.assertEqual(len(normas.filtrar([hallazgo(segundo=50, evidencia="Compra este vape")], DATOS)), 1)

    def test_una_norma_fuera_de_la_lista_se_descarta(self):
        self.assertEqual(normas.filtrar([hallazgo(norma="me_cae_mal")], DATOS), [])

    def test_un_segundo_fuera_del_video_se_descarta(self):
        self.assertEqual(normas.filtrar([hallazgo(segundo=999)], DATOS), [])
        self.assertEqual(normas.filtrar([hallazgo(segundo=-1)], DATOS), [])

    def test_un_hallazgo_sin_explicacion_se_descarta(self):
        self.assertEqual(normas.filtrar([hallazgo(por_que=" ")], DATOS), [])

    def test_una_explicacion_demasiado_larga_se_descarta(self):
        self.assertEqual(normas.filtrar([hallazgo(por_que="x" * 400)], DATOS), [])

    def test_una_norma_sale_una_sola_vez_y_cinco_como_maximo(self):
        repetidos = [hallazgo() for _ in range(3)]
        self.assertEqual(len(normas.filtrar(repetidos, DATOS)), 1)
        varios = [hallazgo(norma=n["id"]) for n in normas.reglas()]
        self.assertEqual(len(normas.filtrar(varios, DATOS)), normas.MAX_HALLAZGOS)

    def test_una_respuesta_rara_no_truena(self):
        self.assertEqual(normas.filtrar(["no es un objeto", {"norma": 3}, {}], DATOS), [])


class Revisar(unittest.TestCase):
    def preparar(self, d: Path) -> None:
        (d / "manifiesto.json").write_text(json.dumps({"duracion_s": 60.0, "tramos": [
            {"inicio_s": i * 1.5, "fin_s": (i + 1) * 1.5} for i in range(40)]}), encoding="utf-8")
        (d / "describir.json").write_text(json.dumps({"tramos": [
            {"tramo": 0, "que_pasa": "Una mano sostiene un vapeador.", "texto_en_pantalla": "Oferta de hoy"}]}), encoding="utf-8")
        (d / "transcribir.json").write_text(json.dumps({"turnos": [
            {"startMs": 12000, "transcript": "Escribe a este número y te lo mando hoy mismo"}, {"startMs": 15000, "transcript": None}]}), encoding="utf-8")
        (d / "resultado.json").write_text(json.dumps({"video": {"titulo": "Compra este vape barato"}}), encoding="utf-8")

    def test_arma_el_resultado_con_nombre_y_fuente_en_el_idioma_del_panel(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(meta_api, "responder", return_value=respuesta([hallazgo()])) as api:
            d = Path(t); self.preparar(d)
            s = normas.revisar(d, "en", "Compra este vape barato")
        h = s["hallazgos"][0]
        self.assertEqual(h["nombre"], "Restricted goods and services")
        self.assertIn("regulated-goods", h["fuente"])
        self.assertEqual(s["revisadas"], len(normas.reglas()))
        enviado = json.dumps(api.call_args.args[1]["input"][1], ensure_ascii=False)
        self.assertIn("DATOS_DEL_VIDEO", enviado)

    def test_si_no_hay_nada_lo_dice_sin_inventar(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(meta_api, "responder", return_value=respuesta([])):
            d = Path(t); self.preparar(d)
            self.assertEqual(normas.revisar(d, "es", "x")["hallazgos"], [])

    def test_la_segunda_vez_no_se_paga(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(meta_api, "responder", return_value=respuesta([])) as api:
            d = Path(t); self.preparar(d)
            normas.revisar(d, "es", "x")
            normas.revisar(d, "es", "x")
        api.assert_called_once()


if __name__ == "__main__":
    unittest.main()
