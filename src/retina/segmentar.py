"""Servicio «segmentar»: MP4 -> tramos alineados a la curva + WAV + MP4 ligero.

La curva de retención de Facebook trae 41 puntos (0 %, 2.5 %, ... 100 % de la
duración), así que el video se parte en 40 tramos iguales: en un video de
96 s cada tramo dura 2.4 s. Cada tramo guarda sus cuadros para el embebido
y su índice es el que usan describir y predecir.

Uso:
    python -m retina.segmentar VIDEO.mp4 --salida CARPETA [--fps 4]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

N_PUNTOS = 41
N_TRAMOS = N_PUNTOS - 1


# Retina revisa el arranque: un video de más de media hora no le aporta y tardaría demasiado en cortarse.
DURACION_MAXIMA_S = 30 * 60
MINIMO_S = 5
# Ningún paso de ffmpeg se queda colgado: pasado este tiempo, la revisión falla con un aviso claro.
TIEMPO_MAXIMO_S = 5 * 60


def tiempo_maximo_s() -> int:
    """RETINA_FFMPEG_TIEMPO_S solo lo baja: la demo en línea no deja que un video pesado ocupe la fila por horas."""
    valor = os.environ.get("RETINA_FFMPEG_TIEMPO_S", "").strip()
    return min(int(valor), TIEMPO_MAXIMO_S) if valor.isdigit() and int(valor) > 0 else TIEMPO_MAXIMO_S


class Aviso(ValueError):
    """Algo que la persona puede arreglar. `clave` dice cuál, para que la app lo diga en su idioma."""

    def __init__(self, clave: str, mensaje: str):
        super().__init__(mensaje)
        self.clave = clave


# ffmpeg abre archivos de cualquiera: solo lee archivos locales y no ve las llaves. Un archivo armado a propósito
# podría pedirle leer el entorno del proceso y dejarlo escrito en lo que produce.
PROTOCOLOS = ("-protocol_whitelist", "file,pipe",
              # y solo los contenedores que la app acepta: sin concat, hls, image2 ni lavfi en un archivo armado a propósito
              "-format_whitelist", "mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,avi,flv")


def entorno_ffmpeg() -> dict:
    return {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME") if k in os.environ}


def _ffmpeg() -> str:
    ruta = os.environ.get("FFMPEG") or shutil.which("ffmpeg")
    if not ruta:
        raise Aviso("sin_ffmpeg", "No encuentro ffmpeg: instálalo, o pon su ruta en la variable FFMPEG.")
    return ruta


def _info(video: Path) -> str:
    # ffmpeg -i escribe la duración y las pistas en stderr; así no dependemos de ffprobe.
    try:
        p = subprocess.run([_ffmpeg(), "-hide_banner", *PROTOCOLOS, "-i", str(video)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120, env=entorno_ffmpeg())
    except subprocess.TimeoutExpired:
        raise Aviso("no_lee", f"ffmpeg no pudo leer {video.name} a tiempo.") from None
    return p.stderr


def duracion_s(video: Path, info: str | None = None) -> float:
    # Solo la línea propia de ffmpeg: un título del archivo podría decir «Duration: 00:00:01.00».
    m = re.search(r"^  Duration: (\d+):(\d+):(\d+\.\d+)", info if info is not None else _info(video), re.M)
    if not m:
        raise Aviso("no_lee", f"No pude leer la duración de {video.name}.")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def pistas(info: str) -> tuple[bool, bool]:
    """(trae imagen, trae audio) según lo que ffmpeg -i dice de sus pistas."""
    # Sin expresión regular y solo al inicio de la línea: ffmpeg imprime aquí el título del archivo, que escribe quien sube el video.
    lineas = [x for x in info.split("\n") if x.lstrip(" ").startswith("Stream #")]
    return (any(": Video:" in x and "attached pic" not in x for x in lineas),  # la portada de un MP3 no es imagen
            any(": Audio:" in x for x in lineas))


def limites_tramos(duracion: float) -> list[tuple[float, float]]:
    paso = duracion / N_TRAMOS
    return [(i * paso, (i + 1) * paso) for i in range(N_TRAMOS)]


# Los dibujos de Muse Image (PNG, JPEG, WebP) que Retina convierte en clip: son nuestros, no de la persona.
PROTOCOLOS_IMAGEN = ("-protocol_whitelist", "file,pipe", "-format_whitelist", "image2,png_pipe,jpeg_pipe,webp_pipe,mjpeg")


def _correr(args: list[str], imagen: bool = False) -> None:
    try:
        p = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *(PROTOCOLOS_IMAGEN if imagen else PROTOCOLOS), *args], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=tiempo_maximo_s(), env=entorno_ffmpeg())
    except subprocess.TimeoutExpired:
        raise Aviso("ffmpeg_lento", f"ffmpeg tardó más de {tiempo_maximo_s() // 60 or 1} minutos y se detuvo.") from None
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[-500:])


def maximo_s() -> int:
    """Hasta cuánto dura un video. RETINA_DURACION_MAXIMA_S solo lo baja: la demo en línea revisa videos cortos."""
    valor = os.environ.get("RETINA_DURACION_MAXIMA_S", "").strip()
    return min(int(valor), DURACION_MAXIMA_S) if valor.isdigit() and int(valor) > 0 else DURACION_MAXIMA_S


def segmentar(video: Path, salida: Path, fps: float = 4.0, lado: int = 256) -> dict:
    salida.mkdir(parents=True, exist_ok=True)
    cuadros_dir = salida / "cuadros"
    cuadros_dir.mkdir(exist_ok=True)
    info = _info(video)
    dur = duracion_s(video, info)
    con_imagen, con_audio = pistas(info)
    if not con_imagen:  # un M4A o un MP3 con portada no es un video
        raise Aviso("sin_imagen", "Ese archivo no trae imagen: Retina revisa videos.")
    if dur < MINIMO_S:  # antes de gastar: en tan poco no hay arranque que revisar
        raise Aviso("muy_corto", f"El video dura menos de {MINIMO_S} segundos: en tan poco no hay arranque que revisar.")
    if dur > maximo_s():
        raise Aviso("muy_largo", f"El video dura más de {maximo_s() // 60} minutos, que es lo que Retina revisa.")

    # Cuadros a fps fijo, lado corto = `lado` px (lo que espera V-JEPA 2).
    # -t en cada paso: la duración de arriba la declara el archivo, y un archivo puede mentir.
    tope = str(maximo_s())
    _correr(["-i", str(video), "-t", tope, "-vf",
             f"fps={fps},scale='if(gt(iw,ih),-2,{lado})':'if(gt(iw,ih),{lado},-2)'",
             "-q:v", "3", str(cuadros_dir / "c%05d.jpg")])
    # Audio para Voice Transcribe: mono, PCM 16 bits, 24 kHz (tasa nativa del modelo).
    # Un video sin audio se revisa igual, solo con lo que se ve (la tarjeta lo dice).
    if con_audio:
        _correr(["-i", str(video), "-t", tope, "-vn", "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le",
                 "-map_metadata", "-1", str(salida / "audio.wav")])
    # Copia ligera para la Files API: menos bytes que subir, mismos cuadros visibles.
    _correr(["-i", str(video), "-t", tope, "-vf", "scale=-2:480", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "28", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart",
             str(salida / "ligero.mp4")])

    cuadros = sorted(cuadros_dir.glob("c*.jpg"))
    tramos = []
    for i, (ini, fin) in enumerate(limites_tramos(dur)):
        # El cuadro k está en el segundo k/fps; se asigna al tramo que lo contiene.
        suyos = [c.name for k, c in enumerate(cuadros) if ini <= k / fps < fin]
        tramos.append({"tramo": i, "inicio_s": round(ini, 3), "fin_s": round(fin, 3),
                       "cuadros": suyos})

    manifiesto = {
        "version": "segmentar-v1",
        "video": video.name,
        "duracion_s": round(dur, 3),
        "n_tramos": N_TRAMOS,
        "fps_cuadros": fps,
        "audio": "audio.wav" if con_audio else None,
        "mp4_ligero": "ligero.mp4",
        "tramos": tramos,
        "tramos_sin_cuadros": [t["tramo"] for t in tramos if not t["cuadros"]],
    }
    (salida / "manifiesto.json").write_text(json.dumps(manifiesto, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    return manifiesto


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("video", type=Path)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--fps", type=float, default=4.0)
    a = ap.parse_args()
    m = segmentar(a.video, a.salida, a.fps)
    print(f"{m['duracion_s']} s · {m['n_tramos']} tramos de {m['duracion_s'] / m['n_tramos']:.2f} s"
          f" · {sum(len(t['cuadros']) for t in m['tramos'])} cuadros"
          f" · tramos sin cuadros: {m['tramos_sin_cuadros'] or 'ninguno'}")


if __name__ == "__main__":
    main()
