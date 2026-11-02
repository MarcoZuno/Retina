"""El escáner de secretos del repo: la regla de códigos internos de producción y el gancho que la corre.

Las pruebas leen `.gitleaks.toml` y ejercitan la expresión con `re`. Los patrones usan solo lo que `re` y RE2 (el motor
de gitleaks) comparten, así que lo que pasa aquí pasa igual en gitleaks: un cambio en la regla no puede dejar pasar un
código ni bloquear el ejemplo inventado sin que se note. Los códigos de prueba se arman en tiempo de ejecución, para
que ni este archivo ni su .pyc contengan uno y disparen el escáner."""
import re
import subprocess
import tomllib
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _pega(*partes: str) -> str:
    """Junta letras y dígitos en ejecución (el compilador no lo pliega a una constante, como haría con «+»)."""
    return "".join(partes)


def _regla():
    cfg = tomllib.loads((RAIZ / ".gitleaks.toml").read_text(encoding="utf-8"))
    regla = next(r for r in cfg["rules"] if r["id"] == "codigo-produccion-badabun")
    permitidos = [re.compile(x) for a in regla.get("allowlists", []) for x in a.get("regexes", [])]
    return re.compile(regla["regex"]), regla.get("secretGroup", 0), permitidos


def _secretos(texto: str) -> list[str]:
    """Lo que gitleaks reportaría de esa línea: cada captura que ningún permiso de la regla exime."""
    patron, grupo, permitidos = _regla()
    return [m.group(grupo) for m in patron.finditer(texto) if not any(p.search(m.group(grupo)) for p in permitidos)]


class ReglaDeCodigos(unittest.TestCase):
    def test_atrapa_codigos_con_el_formato_interno(self):
        for linea in (_pega("codigo = ABCD", "1234567"), _pega("2026-10-05_ABCD", "1234567", "_T.mp4"),
                      _pega("x,ABC", "1234567", ",y"), _pega("WXYZ", "26100555")):
            self.assertTrue(_secretos(linea), linea)

    def test_deja_pasar_los_ejemplos_y_solo_los_ejemplos(self):
        self.assertEqual(_secretos("codigo = XYZ000000N y XYZ0000001"), [])
        self.assertEqual(_secretos(_pega("XYZ", "012345N")), [_pega("XYZ", "012345")])
        self.assertEqual(_secretos(_pega("XYZ", "000001N")), [_pega("XYZ", "000001")])
        self.assertEqual(_secretos(_pega("XYZ", "0000000")), [_pega("XYZ", "0000000")])

    def test_un_ejemplo_no_esconde_al_codigo_de_al_lado(self):
        self.assertEqual(_secretos(_pega("XYZ0000001,ABC", "123456N")), [_pega("ABC", "123456")])

    def test_no_marca_lo_que_no_es_codigo(self):
        for linea in ("sha256 08814e89364d2991", "Muse-Spark-Open-816B-A42B", "PYSEC-2026-4320", "v1.2.3",
                      "ab12345678", "2026-10-31 01:40:59"):
            self.assertEqual(_secretos(linea), [], linea)

    def test_el_permiso_de_los_nombres_de_cache_va_anclado(self):
        cfg = tomllib.loads((RAIZ / ".gitleaks.toml").read_text(encoding="utf-8"))
        regexes = [x for a in cfg.get("allowlists", []) for x in a.get("regexes", [])]
        self.assertTrue(regexes)
        for r in regexes:
            self.assertTrue(r.startswith("^") and r.endswith("$"), r)
            self.assertIsNotNone(re.fullmatch(r, "retina-explicar-v2"))
            self.assertIsNone(re.search(r, _pega("sk_live_retina-explicar-v2_", "9f8e7d6c5b4a3f2e")))


class Gancho(unittest.TestCase):
    def test_corre_pruebas_y_gitleaks_con_fines_de_linea_lf(self):
        crudo = (RAIZ / ".githooks" / "pre-commit").read_bytes()
        self.assertNotIn(b"\r", crudo)
        texto = crudo.decode("utf-8")
        self.assertTrue(texto.startswith("#!/bin/sh\n"))
        self.assertIn("unittest discover -s tests", texto)
        self.assertIn("gitleaks protect --staged", texto)
        self.assertLess(texto.index("python3"), texto.index("python "), "primero python3, luego python")

    def test_es_ejecutable_en_git(self):
        try:
            salida = subprocess.run(["git", "ls-files", "-s", ".githooks/pre-commit"], cwd=RAIZ, capture_output=True,
                                    text=True, timeout=30, check=True).stdout
        except (OSError, subprocess.SubprocessError):
            self.skipTest("sin git")
        if not salida.strip():
            self.skipTest("el gancho no está en el índice de git")
        self.assertTrue(salida.startswith("100755"), salida)

    def test_claude_md_dice_como_activarlo(self):
        self.assertIn("core.hooksPath .githooks", (RAIZ / "CLAUDE.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
