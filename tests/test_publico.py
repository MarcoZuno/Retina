"""El cerebro público: qué deja fuera, que no lleve nombres y que el archivo no traiga nada de un video."""
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
from retina.publico import (ModeloPublico, cargar_modelo, entrenar, firma, motivo_fuera, nombres,  # noqa: E402
                            patrones, titulo_publico)

ARCHIVO = RAIZ / "modelos" / "retina-publico.json"


def _textos(x, ruta=""):
    """Todos los textos que trae un JSON, como valores (las llaves se revisan aparte)."""
    if isinstance(x, str):
        yield ruta, x
    elif isinstance(x, dict):
        for k, v in x.items():
            yield from _textos(v, f"{ruta}.{k}")
    elif isinstance(x, list):
        for v in x:
            yield from _textos(v, ruta)


class QueQuedaFuera(unittest.TestCase):
    def setUp(self):
        self.temas = patrones()

    def video(self, titulo="Así se tejen las bufandas de lana", elegibilidad=0.0):
        return {"titulo": titulo, "elegibilidad": elegibilidad}

    def test_elegib_o_sin_dato_de_elegib_queda_fuera(self):
        self.assertEqual(motivo_fuera(self.video(elegibilidad=None), None, self.temas), "elegibilidad")
        self.assertEqual(motivo_fuera(self.video(elegibilidad=0.3), None, self.temas), "elegibilidad")

    def test_fuera_y_temas_fuera_en_titulo_o_en_lo_que_se_dice(self):
        self.assertEqual(motivo_fuera(self.video("Lo que dijo el figura pública"), None, self.temas), "fuera")
        self.assertEqual(motivo_fuera(self.video("Así murió el cantante"), None, self.temas), "graves")
        self.assertEqual(motivo_fuera(self.video(), [[0.4, "Hoy hablamos de las temas fuera de alcance"]], self.temas), "fuera")
        self.assertEqual(motivo_fuera(self.video("ACCIDENTE en la carretera"), None, self.temas), "graves")  # sin acentos ni mayúsculas

    def test_un_video_ligero_elegibles_si_entra(self):
        self.assertIsNone(motivo_fuera(self.video(), [[0.4, "Mira cómo se teje"]], self.temas))


class SinNombres(unittest.TestCase):
    def test_la_firma_al_final_del_titulo_se_reconoce(self):
        self.assertEqual(firma("Así luce la casa 😱🏠 \nLía Ortúzar").strip(), "Lía Ortúzar")
        self.assertEqual(firma("Sin emoji Lía Ortúzar"), "")
        self.assertEqual(firma("Mira esto 😱 y luego me cuentas qué opinas de todo"), "")

    def test_nombres_de_la_lista_y_firmas_repetidas_salen_del_titulo(self):
        filas = [{"talento": "ZOE QUINTANAR", "titulo": f"Receta {i} 😱 Lía Ortúzar"} for i in range(3)]
        quitar = nombres(filas)
        self.assertTrue({"zoe", "quintanar", "lia", "ortuzar"} <= quitar)
        self.assertEqual(titulo_publico("Zoe prueba la receta 😱 Lía Ortúzar", quitar), "prueba la receta 😱")


class ArchivoPublico(unittest.TestCase):
    """Con datos inventados: el archivo se arma, se abre sin pickle y no trae textos de ningún video."""

    @classmethod
    def setUpClass(cls):
        azar = np.random.default_rng(31)
        inicio, filas, voz = datetime(2025, 1, 1), [], {}
        for i in range(260):
            dur = float(azar.choice([45, 90, 180, 300]))
            filas.append({"codigo": f"ZZQ{i:04d}", "fecha": inicio + timedelta(hours=int(azar.integers(0, 24 * 300))),
                          "dur": dur, "cubeta": cubeta(dur), "talento": str(azar.choice(["ZOE QUINTANAR", "IKER VALDIVIA"])),
                          "archivo": f"2025-01-01 ZZQ{i:04d} ZOE EDITOR receta", "titulo": "Receta casera 😱 Zoe Quintanar",
                          "reel": float(dur < 60), "elegibilidad": 0.0 if i % 9 else 0.5,
                          "curva": np.sort(azar.random(41))[::-1]})
            if i % 2:
                voz[f"ZZQ{i:04d}"] = [[0.5, "hola soy Zoe"], [3.0, "hoy te enseño una receta"]]
        filas.sort(key=lambda x: x["fecha"])
        cls.d = json.loads(json.dumps(entrenar(filas, voz)))
        cls.modelo = ModeloPublico(cls.d)

    def test_no_trae_nombres_codigos_ni_titulos(self):
        texto = json.dumps(self.d, ensure_ascii=False).lower()
        for prohibido in ("zoe", "quintan", "iker", "valdiv", "zzq", "receta", "editor"):
            self.assertNotIn(prohibido, texto.replace("que_es", ""))

    def test_no_publica_conteos(self):
        # Ni cuántos videos tuvieron elegibilidad, fuera de alcance o temas fuera de alcance, ni cuántos hay por duración.
        for llave in ("videos_fuera", "videos_que_aprendio", "videos_por_duracion"):
            self.assertNotIn(llave, self.d)

    def test_predice_con_y_sin_voz_y_da_su_riesgo(self):
        v = {"fecha": datetime(2025, 12, 1, 18), "dur": 90.0, "cubeta": cubeta(90.0), "codigo": "", "talento": "",
             "archivo": "receta", "titulo": "receta", "reel": 0.0}
        con = self.modelo.predecir(v, tramos=[[0.3, "¿Sabías esto?"]])
        sin = self.modelo.predecir(v)
        self.assertEqual((con["cerebro"], sin["cerebro"], con["conoce_al_creador"]), ("cualquier_video", "promedio", False))
        self.assertEqual(sin["curva_predicha"], sin["curva_parecidos"])
        nivel = self.modelo.arranque().predecir(v, np.array(con["curva_parecidos"]))["nivel"]
        self.assertIn(nivel, ("alto", "medio", "bajo"))

    def test_el_modo_publico_no_da_semaforo_y_avisa_en_videos_cortos(self):
        self.assertFalse(self.modelo.semaforo)  # la v1 no pasó y la v2 es exploratoria (docs/decisiones.md)
        corto = {"fecha": datetime(2025, 12, 1, 18), "dur": 20.0, "cubeta": cubeta(20.0), "codigo": "", "talento": "",
                 "archivo": "receta", "titulo": "receta", "reel": 1.0}
        self.assertTrue(self.modelo.predecir(corto)["formato_poco_conocido"])
        reel = {**corto, "dur": 75.0, "cubeta": cubeta(75.0)}  # vertical de más de 30 s: también casi no los vio
        self.assertTrue(self.modelo.predecir(reel)["formato_poco_conocido"])
        self.assertFalse(self.modelo.predecir({**reel, "reel": 0.0})["formato_poco_conocido"])

    def test_un_json_que_no_es_el_cerebro_publico_no_se_abre(self):
        with self.assertRaises(ValueError):
            ModeloPublico({"version": "otra-cosa"})


@unittest.skipUnless(ARCHIVO.exists(), "sin modelos/retina-publico.json")
class ElArchivoDelRepo(unittest.TestCase):
    def test_solo_trae_numeros_y_textos_fijos(self):
        d = json.loads(ARCHIVO.read_text(encoding="utf-8"))
        textos = dict(_textos(d))
        self.assertEqual(set(textos), {".version", ".que_es", ".datos_hasta"})
        self.assertFalse({"videos_fuera", "videos_que_aprendio", "videos_por_duracion"} & set(d))
        self.assertEqual(set(d["arranque"]["W"]), {"con_voz", "sin_voz"})
        self.assertIsInstance(cargar_modelo(ARCHIVO), ModeloPublico)


class MetricasDeMeta(unittest.TestCase):
    """Las métricas de los exports de Meta se leen sin tocar nunca una columna de dinero."""

    def test_ninguna_metrica_viene_de_ingresos(self):
        from retina.metricas_meta import METRICAS, PROHIBIDAS
        for nombres in METRICAS.values():
            for n in nombres:
                self.assertFalse(any(p in n.lower() for p in PROHIBIDAS), n)

    def test_el_export_con_ingresos_se_lee_sin_ingresos(self):
        import csv as _csv
        import tempfile
        from retina.base import CURVA
        from retina.metricas_meta import leer
        cols = ["Identificador de la publicación", "Nombre de la página", "Tipo de publicación", "Alcance",
                "Ingresos estimados (USD)", *[CURVA.format(i) for i in range(41)]]
        with tempfile.TemporaryDirectory() as d:
            with (Path(d) / "x.csv").open("w", encoding="utf-8-sig", newline="") as h:
                w = _csv.writer(h); w.writerow(cols)
                w.writerow(["1", "Pagina", "Videos", "1000", "55.5", *["0.5"] * 41])
            m = leer([Path(d)], "Pagina")["1"]
        self.assertEqual(m["alcance"], 1000.0)
        self.assertNotIn("55.5", json.dumps(m))


if __name__ == "__main__":
    unittest.main()
