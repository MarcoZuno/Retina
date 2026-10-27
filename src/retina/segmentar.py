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


def _ffmpeg() -> str:
    ruta = os.environ.get("FFMPEG") or shutil.which("ffmpeg")
    if not ruta:
        raise RuntimeError("No encuentro ffmpeg: ponlo en el PATH o en la variable FFMPEG.")
    return ruta


def duracion_s(video: Path) -> float:
    # ffmpeg -i escribe la duración en stderr; así no dependemos de ffprobe.
    p = subprocess.run([_ffmpeg(), "-hide_banner", "-i", str(video)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", p.stderr)
    if not m:
        raise RuntimeError(f"No pude leer la duración de {video.name}")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def limites_tramos(duracion: float) -> list[tuple[float, float]]:
    paso = duracion / N_TRAMOS
    return [(i * paso, (i + 1) * paso) for i in range(N_TRAMOS)]


def _correr(args: list[str]) -> None:
    p = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[-500:])


def segmentar(video: Path, salida: Path, fps: float = 4.0, lado: int = 256) -> dict:
    salida.mkdir(parents=True, exist_ok=True)
    cuadros_dir = salida / "cuadros"
    cuadros_dir.mkdir(exist_ok=True)
    dur = duracion_s(video)

    # Cuadros a fps fijo, lado corto = `lado` px (lo que espera V-JEPA 2).
    _correr(["-i", str(video), "-vf",
             f"fps={fps},scale='if(gt(iw,ih),-2,{lado})':'if(gt(iw,ih),{lado},-2)'",
             "-q:v", "3", str(cuadros_dir / "c%05d.jpg")])
    # Audio para Voice Transcribe: mono, PCM 16 bits, 24 kHz (tasa nativa del modelo).
    _correr(["-i", str(video), "-vn", "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le",
             "-map_metadata", "-1", str(salida / "audio.wav")])
    # Copia ligera para la Files API: menos bytes que subir, mismos cuadros visibles.
    _correr(["-i", str(video), "-vf", "scale=-2:480", "-c:v", "libx264", "-preset", "veryfast",
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
        "audio": "audio.wav",
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
