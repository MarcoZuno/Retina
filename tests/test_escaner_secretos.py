"""El escáner de secretos del repo: la regla de códigos internos de producción y el gancho que la corre.

Las pruebas leen `.gitleaks.toml` y ejercitan la expresión con `re`. Los patrones usan solo lo que `re` y RE2 (el motor
de gitleaks) comparten, así que lo que pasa aquí pasa igual en gitleaks: un cambio en la regla no puede dejar pasar un
código ni bloquear el ejemplo inventado sin que se note. Los códigos de prueba se arman en tiempo de ejecución, para
que ni este archivo ni su .pyc contengan uno y disparen el escáner. El gancho se prueba ejecutando su bloque de
cómo escoge el intérprete con `sh`, no leyéndolo: un gancho que solo tuviera las frases en comentarios no pasa."""
import re
import shutil
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
GANCHO = RAIZ / ".githooks" / "pre-commit"


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


def _lineas_de_codigo() -> list[str]:
    """Las líneas del gancho que se ejecutan: sin comentarios ni vacías."""
    return [l for l in GANCHO.read_text(encoding="utf-8").splitlines() if l.strip() and not l.lstrip().startswith("#")]


def _bloque_del_interprete() -> str:
    """Desde `PY=""` hasta la línea que exige que haya quedado uno: lo que elige el intérprete."""
    lineas = GANCHO.read_text(encoding="utf-8").splitlines()
    inicio = next(i for i, l in enumerate(lineas) if l.startswith('PY=""'))
    fin = next(i for i, l in enumerate(lineas) if '[ -n "$PY" ]' in l)
    return "\n".join(lineas[inicio:fin + 1])


def _comprobacion_de_version() -> str:
    """El Python de una línea con el que el gancho decide si un intérprete sirve."""
    m = re.search(r"""-c '([^']*version_info[^']*)'""", GANCHO.read_text(encoding="utf-8"))
    assert m, "el gancho no trae la comprobación de versión"
    return m.group(1)


class Gancho(unittest.TestCase):
    def test_es_sh_con_fines_de_linea_lf(self):
        crudo = GANCHO.read_bytes()
        self.assertNotIn(b"\r", crudo)
        self.assertTrue(crudo.startswith(b"#!/bin/sh\n"))

    def test_los_controles_se_ejecutan_y_frenan_el_commit(self):
        """Cada control está en una línea que corre (no en un comentario) y termina el gancho con 1 si falla."""
        codigo = _lineas_de_codigo()
        for control in ('-m unittest discover -s tests', 'gitleaks protect --staged', 'command -v gitleaks'):
            linea = next((l for l in codigo if control in l), None)
            self.assertIsNotNone(linea, control)
            self.assertRegex(linea, r"\|\| \{.*exit 1; \}\s*$", linea)

    def test_busca_python3_luego_python_luego_py_y_exige_3_12(self):
        self.assertIn("for c in python3 python py; do", _bloque_del_interprete())
        comprobacion = _comprobacion_de_version()
        for version, esperado in (((3, 11, 9), 1), ((3, 12, 0), 0), ((3, 14, 1), 0)):
            r = subprocess.run([sys.executable, "-c", f"import sys; sys.version_info = {version}; {comprobacion}"],
                               capture_output=True, timeout=60)
            self.assertEqual(r.returncode, esperado, (version, r.stderr))
        self.assertEqual(subprocess.run([sys.executable, "-c", comprobacion], timeout=60).returncode, 0)

    def _correr_bloque(self, python3: int, python: int, py: int) -> subprocess.CompletedProcess:
        """Corre el bloque bajo `sh` con los tres intérpretes sustituidos por funciones que devuelven lo que se les diga."""
        sh = shutil.which("sh")
        if not sh:
            self.skipTest("sin sh")
        guion = (f"python3() {{ return {python3}; }}; python() {{ return {python}; }}; py() {{ return {py}; }}\n"
                 f"{_bloque_del_interprete()}\n"
                 'echo "PY=$PY"\n')
        return subprocess.run([sh, "-c", guion], capture_output=True, text=True, encoding="utf-8", timeout=60)

    def test_toma_el_primero_que_sirve(self):
        self.assertIn("PY=python3", self._correr_bloque(0, 0, 0).stdout)
        self.assertIn("PY=python", self._correr_bloque(1, 0, 0).stdout.replace("PY=python3", ""))
        self.assertIn("PY=py\n", self._correr_bloque(1, 1, 0).stdout)

    def test_sin_interprete_que_sirva_no_hay_commit(self):
        r = self._correr_bloque(1, 1, 127)
        self.assertEqual(r.returncode, 1)
        self.assertIn("No encuentro Python", r.stdout + r.stderr)
        self.assertNotIn("PY=", r.stdout)

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
