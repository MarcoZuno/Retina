"""Al final de la corrida (el nombre lo deja de último): las pruebas no escribieron en mis-revisiones/, que es del uso real
de quien corre Retina (B21). Si una prueba llama a la API o al registro de gasto sin RETINA_COSTOS, aquí se nota.
"""
from __future__ import annotations

import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CARPETA = RAIZ / "mis-revisiones"


def foto() -> dict:
    return {str(p): p.stat().st_mtime_ns for p in CARPETA.rglob("*")} if CARPETA.exists() else {}


ANTES = foto()  # al importar, antes de que corra cualquier prueba


class SinResiduos(unittest.TestCase):
    def test_las_pruebas_no_tocaron_mis_revisiones(self):
        despues = foto()
        nuevos = sorted(set(despues) - set(ANTES))
        cambiados = sorted(p for p in ANTES if p in despues and despues[p] != ANTES[p])
        self.assertEqual((nuevos, cambiados), ([], []), "alguna prueba escribió en mis-revisiones/: que use RETINA_COSTOS o una carpeta temporal")


if __name__ == "__main__":
    unittest.main()
