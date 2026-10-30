"""Cobertura que faltaba (B21): la medición de SAM sin llamar a la API, y una subida real por HTTP al servidor local.
Corren con: python -m unittest discover -s tests   (desde la raíz del repo)
"""
from __future__ import annotations

import functools
import hashlib
import http.client
import http.server
import json
import socket
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from retina import app, meta_api, sam  # noqa: E402


def mascara(unos: int, de: int = 4):
    return types.SimpleNamespace(width=2, height=de // 2, unos=unos)


def registro(cuadro: int, unos: int):
    return types.SimpleNamespace(kind="mask", frame=types.SimpleNamespace(frame_index=cuadro), mask=mascara(unos))


class MedirClipDeSam(unittest.TestCase):
    """sam._medir_clip: aparta el gasto, sube el clip, mide y siempre registra y borra. Sin red y sin meta_sam_parser."""

    def setUp(self):
        self.api = mock.MagicMock()
        for nombre in ("reservar", "subir_archivo", "borrar_archivo", "liberar", "_registrar"):
            parche = mock.patch.object(meta_api, nombre, getattr(self.api, nombre))
            parche.start()
            self.addCleanup(parche.stop)
        self.api.reservar.return_value = "r1"
        self.api.subir_archivo.return_value = "f1"
        # decode_mask_to_raster: la lista de pixeles encendidos de la máscara falsa
        falso = types.ModuleType("meta_sam_parser")
        falso.decode_mask_to_raster = lambda m: [1] * m.unos + [0] * (m.width * m.height - m.unos)
        parche = mock.patch.dict(sys.modules, {"meta_sam_parser": falso})
        parche.start()
        self.addCleanup(parche.stop)

    def resultado(self, estado="completed", registros=()):
        return types.SimpleNamespace(outcome=types.SimpleNamespace(status=estado, reason="x"), records=list(registros))

    def medir(self, resultado, clip=lambda: Path("clip.mp4"), concepto="dog", segundos=3):
        with mock.patch.object(sam, "_segmentar"), mock.patch.object(sam.asyncio, "run", return_value=resultado):
            return sam._medir_clip(clip, concepto, segundos)

    def test_un_concepto_que_no_se_puede_buscar_ni_aparta_gasto(self):
        r = self.medir(self.resultado(), concepto="una persona sonriendo")
        self.assertIn("error", r)
        self.api.reservar.assert_not_called()
        self.api.subir_archivo.assert_not_called()

    def test_mide_donde_y_cuanto_se_ve(self):
        # cuadro 0 con dos máscaras (2 + 2 de 4 px), cuadro 5 con una de 1 de 4, y una máscara vacía en el 7 que no cuenta
        r = self.medir(self.resultado(registros=[registro(0, 2), registro(0, 2), registro(5, 1), registro(7, 0)]))
        self.assertTrue(r["aparece"])
        self.assertEqual(r["primer_segundo"], 0.0)
        self.assertEqual(r["pct_de_cuadros_donde_se_ve"], round(100 * 2 / (3 * sam.FPS)))
        self.assertEqual(r["pct_maximo_del_cuadro"], 100.0)  # 4 de 4 px: se topa en 100, nunca más

    def test_si_no_hay_mascaras_dice_que_no_aparece(self):
        r = self.medir(self.resultado(registros=[registro(2, 0)]))
        self.assertEqual((r["aparece"], r["primer_segundo"], r["pct_de_cuadros_donde_se_ve"]), (False, None, 0))

    def test_aparta_el_minimo_que_cobra_la_api_y_registra_y_borra(self):
        self.medir(self.resultado(), segundos=1)  # 10 cuadros, pero la API cobra al menos 50
        self.assertAlmostEqual(self.api.reservar.call_args.args[1], sam.MIN_CUADROS_COBRADOS * sam.USD_POR_CUADRO)
        self.api._registrar.assert_called_once()
        self.assertEqual(self.api._registrar.call_args.args[4], "r1")  # cierra la reserva que abrió
        self.api.borrar_archivo.assert_called_once_with("f1")

    def test_si_sam_no_termina_se_dice_y_se_cobra_igual(self):
        r = self.medir(self.resultado(estado="failed"))
        self.assertIn("SAM no terminó", r["error"])
        self.api._registrar.assert_called_once()
        self.api.borrar_archivo.assert_called_once()

    def test_si_no_se_pudo_preparar_el_clip_se_libera_lo_apartado(self):
        def mal():
            raise OSError("ffmpeg")
        with self.assertRaises(OSError):
            self.medir(self.resultado(), clip=mal)
        self.api.liberar.assert_called_once_with("r1")
        self.api._registrar.assert_not_called()


class SubidaPorHttp(unittest.TestCase):
    """POST /api/revisar de verdad contra el servidor local: los bytes llegan completos y un corte no deja basura."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.casos = Path(self.tmp.name)
        self.fila = mock.Mock()
        clase = type("Manejador", (app.ConSubida,), {
            "casos": self.casos, "fila": self.fila, "talentos": [], "modelos": {"modelo": None, "arranque": None, "voz": None},
            "hosts": ("127.0.0.1", "localhost"), "en_linea": None})
        self.servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(clase, directory=str(RAIZ)))
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.addCleanup(self.servidor.server_close)
        self.addCleanup(self.servidor.shutdown)
        parche = mock.patch.object(app, "salud", return_value={"ffmpeg": True, "llave": True})
        parche.start()
        self.addCleanup(parche.stop)
        self.cabeceras = {"Host": "127.0.0.1", "X-Retina": "1", "X-Retina-Titulo": "Pan de masa madre",
                          "X-Retina-Fecha": "2026-11-05 10:00", "X-Retina-Publicado": "0"}

    def test_un_mp4_de_varios_megas_llega_completo_y_entra_a_la_fila(self):
        cuerpo = b"\x00\x00\x00\x18ftypmp42" + bytes(range(256)) * (3 * 4096)  # ~3 MB: más de un trozo de lectura
        c = http.client.HTTPConnection("127.0.0.1", self.servidor.server_port, timeout=10)
        c.request("POST", "/api/revisar", cuerpo, self.cabeceras)
        r = c.getresponse()
        id_ = json.loads(r.read())["id"]
        c.close()
        self.assertEqual(r.status, 202)
        guardado = (self.casos / id_ / "video.mp4").read_bytes()
        self.assertEqual(hashlib.sha256(guardado).hexdigest(), hashlib.sha256(cuerpo).hexdigest())
        self.fila.submit.assert_called_once()
        self.assertEqual(self.fila.submit.call_args.args[1], self.casos / id_)

    def test_una_subida_cortada_a_la_mitad_no_deja_carpeta_ni_entra_a_la_fila(self):
        s = socket.create_connection(("127.0.0.1", self.servidor.server_port), timeout=10)
        encabezado = "".join(f"{k}: {v}\r\n" for k, v in {**self.cabeceras, "Content-Length": str(5_000_000)}.items())
        s.sendall(f"POST /api/revisar HTTP/1.1\r\n{encabezado}\r\n".encode() + b"\x00\x00\x00\x18ftypmp42" + b"x" * 1000)
        s.shutdown(socket.SHUT_WR)  # la persona cerró la pestaña: no llegan los 5 MB prometidos
        respuesta = b""
        while trozo := s.recv(4096):
            respuesta += trozo
        s.close()
        self.assertIn(b" 400 ", respuesta.split(b"\r\n", 1)[0])
        self.assertEqual(list(self.casos.iterdir()), [])
        self.fila.submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
