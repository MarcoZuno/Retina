"""La ficha del arranque: se valida, se convierte en rasgos y, si el archivo público la trae, entra al número."""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from retina.curvas import cubeta  # noqa: E402
from retina.ficha import N_FICHA, entrada, ficha_a_vector, leer_arreglo, valida  # noqa: E402
from retina.publico import ModeloPublico, entrenar  # noqa: E402

BUENA = {"n": 1, "gancho": "pregunta", "presenta_antes_del_tema": False, "tema_en_la_primera_frase": True,
         "promete_algo_visible": False, "cifra_al_inicio": True, "pide_interaccion": False, "claridad": 4,
         "curiosidad": 5, "emocion": "sorpresa"}


class Ficha(unittest.TestCase):
    def test_se_valida_y_lo_raro_se_tira(self):
        self.assertEqual(valida(BUENA)["gancho"], "pregunta")
        self.assertIsNone(valida({**BUENA, "gancho": "inventado"}))
        self.assertIsNone(valida({**BUENA, "claridad": 9}))
        self.assertIsNone(valida({k: v for k, v in BUENA.items() if k != "emocion"}))

    def test_el_arreglo_se_encuentra_aunque_venga_con_texto_alrededor(self):
        self.assertEqual(leer_arreglo('Aquí va:\n[{"n": 1}]\nlisto')[0]["n"], 1)
        with self.assertRaises(ValueError):
            leer_arreglo("sin arreglo")

    def test_rasgos_de_la_ficha(self):
        v = ficha_a_vector(valida(BUENA))
        self.assertEqual(len(v), N_FICHA)
        self.assertEqual(v[-1], 1.0)  # hay ficha
        self.assertEqual(v.sum(), 1 + 1 + 1 + 1 + 0.5 + 1.0 + 1)  # gancho, emoción, 2 sí, claridad, curiosidad, hay ficha
        self.assertFalse(ficha_a_vector(None).any())

    def test_un_video_sin_voz_se_anota_solo_con_su_titulo(self):
        self.assertIn("(sin voz)", entrada(1, "Un título", None))
        self.assertIn("VOZ DESDE EL SEGUNDO 0.5", entrada(2, "Otro", [[0.5, "hola qué tal"]]))


class FichaEnElNumero(unittest.TestCase):
    def test_el_archivo_con_fichas_las_usa_al_predecir(self):
        azar = np.random.default_rng(41)
        inicio, filas, voz, fichas = datetime(2025, 1, 1), [], {}, {}
        for i in range(240):
            dur = float(azar.choice([45, 90, 180]))
            cod = f"ZZQ{i:04d}"
            filas.append({"codigo": cod, "fecha": inicio + timedelta(hours=int(azar.integers(0, 24 * 300))), "dur": dur,
                          "cubeta": cubeta(dur), "talento": "", "archivo": "receta", "titulo": "Receta casera", "reel": 0.0,
                          "incluir": True, "curva": np.sort(azar.random(41))[::-1]})
            voz[cod] = [[0.5, "hola"], [3.0, "hoy te enseño"]]
            fichas[cod] = valida({**BUENA, "gancho": str(azar.choice(["pregunta", "presentacion"]))})
        filas.sort(key=lambda x: x["fecha"])
        d = json.loads(json.dumps(entrenar(filas, voz, fichas)))
        self.assertTrue(d["rasgos"]["ficha"])
        m = ModeloPublico(d)
        v = {"fecha": datetime(2025, 12, 1, 18), "dur": 90.0, "cubeta": cubeta(90.0), "codigo": "", "talento": "",
             "archivo": "receta", "titulo": "receta", "reel": 0.0}
        a = m.predecir(v, tramos=[[0.3, "¿Sabías?"]], ficha=valida(BUENA))["curva_predicha"]
        b = m.predecir(v, tramos=[[0.3, "¿Sabías?"]], ficha=valida({**BUENA, "gancho": "presentacion"}))["curva_predicha"]
        self.assertEqual(len(a), 41)
        self.assertNotEqual(a, b)  # la ficha cambia el número


if __name__ == "__main__":
    unittest.main()
