"""Lo que llega de cualquier persona: videos sin audio, archivos sin imagen, audios largos y otro idioma."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import wave
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from retina.segmentar import MINIMO_S, Aviso, pistas, segmentar  # noqa: E402
from retina.transcribir import idioma_de, recortar  # noqa: E402

CON_AUDIO = """Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'x.mp4':
  Duration: 00:01:30.00, start: 0.000000, bitrate: 900 kb/s
  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p, 1280x720, 25 fps
  Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6134706D), 44100 Hz, stereo, fltp, 128 kb/s"""
SOLO_AUDIO_CON_PORTADA = """Input #0, mp3, from 'x.mp3':
  Duration: 00:03:00.00, start: 0.000000, bitrate: 128 kb/s
  Stream #0:0: Audio: mp3, 44100 Hz, stereo, fltp, 128 kb/s
  Stream #0:1: Video: mjpeg (Baseline), yuvj420p, 600x600, 90k tbr (attached pic)"""


class Pistas(unittest.TestCase):
    def test_video_con_audio(self):
        self.assertEqual(pistas(CON_AUDIO), (True, True))

    def test_video_sin_audio(self):
        self.assertEqual(pistas(CON_AUDIO.rsplit("\n", 1)[0]), (True, False))

    def test_un_audio_con_portada_no_es_video(self):
        self.assertEqual(pistas(SOLO_AUDIO_CON_PORTADA), (False, True))

    def test_el_titulo_del_archivo_no_finge_pistas(self):
        # ffmpeg imprime el título del archivo: es lo único de esta salida que escribe quien sube el video.
        for titulo in ("Stream #0:0: Video: h264", "x   Stream #0:0: Video: h264", "x\x85  Stream #0:0: Audio: aac"):
            self.assertEqual(pistas(f"  Metadata:\n    title           : {titulo}\n"), (False, False), repr(titulo))

    def test_un_titulo_enorme_no_cuelga_la_revision(self):
        # 2 MB, lo que cabe en un título: con la búsqueda vieja esto tardaba horas y detenía todo el proceso.
        for relleno in ("Stream #" * 250_000, "x   Stream #" + "a" * 2_000_000):
            inicio = time.monotonic()
            pistas(f"    title           : {relleno}\n{CON_AUDIO}")
            self.assertLess(time.monotonic() - inicio, 1)


class Idioma(unittest.TestCase):
    def test_ingles_espanol_y_sin_pistas(self):
        self.assertEqual(idioma_de("How to fix the opening of your video in three steps"), "en")
        self.assertEqual(idioma_de("Así se tejen las bufandas de lana que nadie te enseñó"), "es")
        self.assertIsNone(idioma_de("Tutorial"))
        self.assertIsNone(idioma_de(""))

    def test_un_espanol_corto_no_se_queda_sin_idioma_por_las_palabras_que_comparte_con_el_portugues(self):
        # Un título y las primeras 60 palabras de un video en español (inventado). «de», «que», «para», «a» y «no» también
        # son portuguesas o francesas: con el margen contado sobre todas las palabras comunes, el español no sacaba ventaja,
        # el inicio se escribía en el idioma del panel (inglés) y la comprobación «tema» fallaba las tres vueltas.
        texto = ("Gatito no quiso dormir para cuidar a sus hermanos. Ahorita nos acabamos de encontrar a este gatito que la "
                 "verdad sí se ve bastante mal. Cuando le ofrecimos agua pensamos que se la iba a tomar toda. Se veía cansado "
                 "y con muchísima sed. No, yo me imagino cuántos días estuvo sin tomar nada, pero en lugar de tomar se fue a "
                 "buscar a los demás")
        self.assertEqual(idioma_de(texto), "es")
        self.assertEqual(idioma_de("Gatito no quiso dormir para cuidar a sus hermanos"), "es")
        self.assertEqual(idioma_de("A quick fix for a slow laptop"), "en")  # «a» también es inglesa: no inclina al español


class Recortar(unittest.TestCase):
    def wav(self, carpeta: Path, segundos: float) -> Path:
        ruta = carpeta / "audio.wav"
        with wave.open(str(ruta), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(1000)
            w.writeframes(b"\x00\x00" * int(segundos * 1000))
        return ruta

    def test_un_audio_corto_se_manda_tal_cual(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = self.wav(Path(d), 30)
            self.assertEqual(recortar(ruta, 60), (ruta, None))

    def test_un_audio_largo_se_recorta_y_dice_hasta_donde(self):
        with tempfile.TemporaryDirectory() as d:
            corto, hasta = recortar(self.wav(Path(d), 90), 60)
            self.assertEqual(hasta, 60.0)
            with wave.open(str(corto), "rb") as w:
                self.assertEqual(w.getnframes(), 60 * 1000)


FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg")


@unittest.skipUnless(FFMPEG, "sin ffmpeg en este equipo")
class SegmentarDeVerdad(unittest.TestCase):
    def ffmpeg(self, *args):
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True, capture_output=True)

    def test_un_video_sin_audio_se_corta_sin_audio(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.ffmpeg("-f", "lavfi", "-i", f"color=c=gray:s=320x240:d={MINIMO_S + 1}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        str(d / "mudo.mp4"))
            m = segmentar(d / "mudo.mp4", d / "caso")
            self.assertIsNone(m["audio"])
            self.assertFalse((d / "caso" / "audio.wav").exists())
            self.assertTrue((d / "caso" / "ligero.mp4").exists())

    def test_un_video_de_menos_de_5_segundos_se_rechaza_antes_de_gastar(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=320x240:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(d / "corto.mp4"))
            with self.assertRaises(Aviso) as e:
                segmentar(d / "corto.mp4", d / "caso")
            self.assertEqual(e.exception.clave, "muy_corto")

    def test_un_audio_solo_se_rechaza_con_su_clave(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-c:a", "aac", str(d / "voz.m4a"))
            with self.assertRaises(Aviso) as e:
                segmentar(d / "voz.m4a", d / "caso")
            self.assertEqual(e.exception.clave, "sin_imagen")


if __name__ == "__main__":
    unittest.main()
