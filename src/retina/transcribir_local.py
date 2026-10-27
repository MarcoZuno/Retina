"""Transcripción con tiempos de los videos de la base que tienen archivo y no tienen voz.

Para entrenar y medir (no es el servicio del panel, que usa Voice Transcribe de
Meta): lee el audio del archivo final con ffmpeg, lo pasa por Whisper en la
GPU local y escribe `estado_wh_retina.jsonl` en el mismo formato que las
transcripciones previas, para que `retina.base` lo junte solo.
Reanudable; para pararlo limpio, crear un archivo PARAR junto al estado.

Uso (con el Python que tenga faster-whisper):
    python -m retina.transcribir_local --base BASE.csv --indice-nas indice.json --estado CARPETA \
        [--cuda-bin CARPETA_CUBLAS] [--anio-desde 2025]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from queue import Queue

import numpy as np

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
# Frases que Whisper inventa sobre música o silencio.
FANTASMAS = re.compile(r"amara\.org|subt[ií]tulos (realizados |hechos )?por|subtitulado por", re.I)


def audio_16k(ruta: str) -> np.ndarray:
    p = subprocess.run([FFMPEG, "-v", "error", "-i", ruta, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1"],
                       capture_output=True, timeout=600)
    return np.frombuffer(p.stdout, np.int16).astype(np.float32) / 32768.0


def limpiar(segmentos) -> list[list]:
    tramos, previo, repetido = [], None, 0
    for s in segmentos:
        t = re.sub(r"\s+", " ", s.text).strip()
        if not t or FANTASMAS.search(t):
            continue
        repetido = repetido + 1 if t == previo else 0
        if repetido >= 2:
            continue  # Whisper a veces se queda repitiendo la misma frase
        previo = t
        tramos.append([round(s.start, 1), t])
    return tramos


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--indice-nas", type=Path, required=True)
    ap.add_argument("--estado", type=Path, required=True)
    ap.add_argument("--cuda-bin", type=Path)
    ap.add_argument("--anio-desde", type=int, default=2025)
    ap.add_argument("--modelo", default="large-v3-turbo")
    a = ap.parse_args()
    if a.cuda_bin and a.cuda_bin.is_dir():
        os.add_dll_directory(str(a.cuda_bin)); os.environ["PATH"] = f"{a.cuda_bin};{os.environ['PATH']}"
    from faster_whisper import BatchedInferencePipeline, WhisperModel

    idx = json.loads(a.indice_nas.read_text(encoding="utf-8"))
    a.estado.mkdir(parents=True, exist_ok=True)
    salida = a.estado / "estado_wh_retina.jsonl"
    hechos = set()
    if salida.exists():
        hechos = {json.loads(l)["id"] for l in salida.open(encoding="utf-8") if l.strip()}
    with a.base.open(encoding="utf-8-sig", newline="") as f:
        filas = [r for r in csv.DictReader(f) if r["tiene_archivo"] == "1" and not r["voz"]
                 and int(r["anio"]) >= a.anio_desde and r["video_id"] and r["video_id"] not in hechos]
    print(f"por transcribir: {len(filas)}", flush=True)
    parar = a.estado / "PARAR"

    cola: Queue = Queue(maxsize=6)

    def leer():
        for r in filas:
            if parar.exists():
                break
            ruta = idx.get(r["archivo_nombre"])
            try:
                cola.put((r, audio_16k(ruta) if ruta else None, None if ruta else "sin archivo en la NAS"))
            except Exception as e:  # noqa: BLE001  un archivo malo no detiene el lote
                cola.put((r, None, f"{type(e).__name__}: {e}"[:200]))
        cola.put(None)

    threading.Thread(target=leer, daemon=True).start()
    modelo = BatchedInferencePipeline(model=WhisperModel(a.modelo, device="cuda", compute_type="float16"))
    n, t0 = 0, time.time()
    with salida.open("a", encoding="utf-8", newline="\n") as out:
        while (item := cola.get()) is not None:
            r, audio, error = item
            d = {"clave": r["codigo_produccion"], "id": r["video_id"], "ok": False, "motor": f"whisper {a.modelo}",
                 "duracion": r["duracion_s"], "titulo": r["titulo"]}
            if error:
                d["error"] = error
            elif len(audio) > 16000:
                segs, _ = modelo.transcribe(audio, language="es", batch_size=8, vad_filter=True)
                tramos = limpiar(segs)
                d.update(ok=bool(tramos), tramos=tramos, palabras=sum(len(t.split()) for _, t in tramos))
            out.write(json.dumps(d, ensure_ascii=False) + "\n"); out.flush()
            n += 1
            if n % 50 == 0:
                print(f"{n}/{len(filas)} · {(time.time() - t0) / n:.1f} s por video", flush=True)
    print(f"terminó: {n} videos en {(time.time() - t0) / 60:.0f} min", flush=True)


if __name__ == "__main__":
    main()
