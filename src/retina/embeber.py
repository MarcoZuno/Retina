"""Servicio «embeber»: video -> un vector por tramo con V-JEPA 2 (pesos abiertos, local).

Se toman 2 cuadros por tramo (80 en total, 256x256). V-JEPA 2 agrupa los
cuadros de 2 en 2 en el tiempo, así que su salida trae exactamente 40
posiciones temporales: una por tramo de la curva. Cada vector es el promedio
de los 256 parches espaciales de su tramo.

Uso:
    python -m retina.embeber video VIDEO.mp4 --salida VECTORES.npy
    python -m retina.embeber lote --pares PARES.csv --raiz CARPETA [--raiz ...] \
        --salida CARPETA --n 200
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import subprocess
import time
from pathlib import Path

import numpy as np

from .segmentar import N_TRAMOS, _ffmpeg, duracion_s

MODELO = os.environ.get("RETINA_VJEPA", "facebook/vjepa2-vitl-fpc64-256")
CUADROS_POR_TRAMO = 2
LADO = 256


def cuadros(video: Path, rapido: bool = False, gpu: bool = True) -> np.ndarray:
    return cuadros_y_audio(video, rapido, gpu)[0]


def cuadros_y_audio(video: Path, rapido: bool = False, gpu: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """80 cuadros RGB uniformes en el tiempo, recorte central cuadrado de 256 px.

    Se decodifica en la GPU (NVDEC): 7 s contra 10 s en CPU para un export de
    100 s a 1080x1920. Con `rapido` solo se leen los cuadros clave (~1 por
    segundo en estos exports): 3 s, a cambio de repetir cuadros en los tramos
    cortos.
    """
    dur = duracion_s(video)
    n = N_TRAMOS * CUADROS_POR_TRAMO
    filtro = (f"fps={n}/{dur:.4f},scale='if(gt(iw,ih),-2,{LADO})':'if(gt(iw,ih),{LADO},-2)',"
              f"crop={LADO}:{LADO}")
    entrada = ["-skip_frame", "nokey"] if rapido else (["-hwaccel", "cuda"] if gpu else [])
    # En la misma lectura sale el audio (mono, 8 kHz) a un archivo temporal: la NAS se lee una vez.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.raw"
        p = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", *entrada, "-i", str(video),
                            "-map", "0:v:0", "-vf", filtro, "-frames:v", str(n), "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "pipe:1",
                            "-map", "0:a:0?", "-ac", "1", "-ar", str(TASA_AUDIO), "-f", "s16le", str(wav)],
                           capture_output=True)
        if p.returncode != 0:
            raise RuntimeError(p.stderr.decode(errors="replace")[-400:])
        audio = np.fromfile(wav, dtype=np.int16) if wav.exists() else np.zeros(0, dtype=np.int16)
    arr = np.frombuffer(p.stdout, dtype=np.uint8).reshape(-1, LADO, LADO, 3)
    if len(arr) < n:  # videos que terminan antes del último cuadro: se repite el final
        arr = np.concatenate([arr, np.repeat(arr[-1:], n - len(arr), axis=0)])
    return arr[:n], rasgos_audio(audio)


TASA_AUDIO = 8000


def rasgos_audio(audio: np.ndarray) -> np.ndarray:
    """Por tramo: volumen medio (dB), volumen bajo (p10, dB), fracción en silencio y cruces por cero.

    Ventanas de 50 ms; silencio = por debajo de -45 dB. Sin audio, todo en silencio.
    """
    salida = np.zeros((N_TRAMOS, 4), dtype=np.float32)
    salida[:, :2], salida[:, 2] = -90.0, 1.0
    if len(audio) < N_TRAMOS * 400:
        return salida
    x = audio.astype(np.float32) / 32768
    for i, trozo in enumerate(np.array_split(x, N_TRAMOS)):
        v = trozo[: len(trozo) // 400 * 400].reshape(-1, 400)  # 400 muestras = 50 ms a 8 kHz
        db = 20 * np.log10(np.sqrt(np.mean(v ** 2, axis=1)) + 1e-6)
        cruces = np.mean(np.abs(np.diff(np.sign(v), axis=1)) > 0)
        salida[i] = [db.mean(), np.percentile(db, 10), np.mean(db < -45), cruces]
    return salida


class Embebedor:
    def __init__(self, modelo: str = MODELO):
        import torch
        from transformers import AutoModel, AutoVideoProcessor
        self.torch = torch
        self.dev = "cuda" if torch.cuda.is_available() else "cpu"
        self.dtype = torch.float16 if self.dev == "cuda" else torch.float32
        self.proc = AutoVideoProcessor.from_pretrained(modelo)
        self.modelo = AutoModel.from_pretrained(modelo, dtype=self.dtype,
                                                attn_implementation="sdpa").to(self.dev).eval()

    def __call__(self, video: np.ndarray) -> np.ndarray:
        torch = self.torch
        x = self.proc(torch.from_numpy(np.ascontiguousarray(video).copy()).permute(0, 3, 1, 2),
                      return_tensors="pt")
        x = x["pixel_values_videos"].to(self.dev, self.dtype)
        with torch.inference_mode():
            h = self.modelo.get_vision_features(x) if hasattr(self.modelo, "get_vision_features") \
                else self.modelo(pixel_values_videos=x).last_hidden_state
        h = h.float().reshape(1, N_TRAMOS, -1, h.shape[-1])  # (1, 40 tiempos, 256 parches, d)
        return h.mean(dim=2)[0].cpu().numpy().astype(np.float16)


def indice_nas(raices: list[Path], cache: Path) -> dict[str, str]:
    """Nombre de archivo -> ruta completa, recorriendo una vez las carpetas de exports."""
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    idx = {}
    for raiz in raices:
        for dirpath, _, archivos in os.walk(raiz):
            for a in archivos:
                if a.lower().endswith(".mp4"):
                    idx.setdefault(a, os.path.join(dirpath, a))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
    return idx


def lote(pares: Path, raices: list[Path], salida: Path, n: int, rapido: bool = False,
         hilos: int = 3, semilla: int = 20261027) -> None:
    """Embebe hasta `n` videos al azar (reanudable: salta los que ya tienen vector).

    Mientras la GPU corre el modelo, `hilos` procesos de ffmpeg leen los
    siguientes videos; la NAS se lee en solo lectura.
    """
    from concurrent.futures import ThreadPoolExecutor

    salida.mkdir(parents=True, exist_ok=True)
    with pares.open(encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))
    random.Random(semilla).shuffle(filas)
    idx = indice_nas(raices, salida / "indice_nas.json")
    hechos = sum(1 for r in filas if (salida / f"{r['codigo_produccion']}.npy").exists())
    pendientes = [r for r in filas if not (salida / f"{r['codigo_produccion']}.npy").exists()]
    pendientes = pendientes[:max(0, n - hechos)]
    emb = Embebedor()
    # NVDEC se satura con ~3 videos a la vez; los demás lectores decodifican en CPU.
    import threading
    turnos_gpu = threading.Semaphore(3)

    def leer(r):
        t0 = time.time()
        ruta = idx.get(r["archivo_nombre"])
        if not ruta:
            raise FileNotFoundError("sin archivo en la NAS")
        gpu = turnos_gpu.acquire(blocking=False)
        try:
            v, audio = cuadros_y_audio(Path(ruta), rapido, gpu=gpu)
        finally:
            if gpu:
                turnos_gpu.release()
        np.save(salida / f"{r['codigo_produccion']}.audio.npy", audio)  # no depende de la GPU
        return v, time.time() - t0

    registro = (salida / "registro.jsonl").open("a", encoding="utf-8")
    inicio = time.time()
    with ThreadPoolExecutor(max_workers=hilos) as pool:
        # Ventana corrida: solo hilos*2 videos leídos por adelantado (cada uno pesa ~16 MB en memoria).
        cola = iter(pendientes)
        futuros = [(r, pool.submit(leer, r)) for r, _ in zip(cola, range(hilos * 2))]
        i = 0
        while futuros:
            r, fut = futuros.pop(0)
            siguiente = next(cola, None)
            if siguiente is not None:
                futuros.append((siguiente, pool.submit(leer, siguiente)))
            i += 1
            fila = {"codigo": r["codigo_produccion"], "ok": False}
            try:
                v, seg_leer = fut.result()
                t1 = time.time()
                np.save(salida / f"{r['codigo_produccion']}.npy", emb(v))
                fila.update(ok=True, seg_leer=round(seg_leer, 1), seg_modelo=round(time.time() - t1, 2))
                hechos += 1
            except Exception as e:  # un video malo no detiene el lote
                fila["error"] = str(e)[:200]
            registro.write(json.dumps(fila, ensure_ascii=False) + "\n"); registro.flush()
            print(f"{hechos}/{n} · {(time.time() - inicio) / i:.1f} s por video · {fila}", flush=True)


def rellenar_audio(salida: Path, hilos: int = 4) -> None:
    """Saca solo el audio de los videos que ya tienen vector pero no audio (lotes viejos)."""
    from concurrent.futures import ThreadPoolExecutor

    idx = json.loads((salida / "indice_nas.json").read_text(encoding="utf-8"))
    pares = {}
    for p in salida.glob("*.npy"):
        if not p.name.endswith(".audio.npy") and not (salida / f"{p.stem}.audio.npy").exists():
            pares[p.stem] = None
    # el índice va por nombre de archivo: se busca el que contiene el código
    for nombre, ruta in idx.items():
        for codigo in list(pares):
            if pares[codigo] is None and codigo in nombre:
                pares[codigo] = ruta

    def uno(item):
        codigo, ruta = item
        if not ruta:
            return codigo, "sin archivo"
        p = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", ruta, "-vn",
                            "-ac", "1", "-ar", str(TASA_AUDIO), "-f", "s16le", "pipe:1"], capture_output=True)
        np.save(salida / f"{codigo}.audio.npy", rasgos_audio(np.frombuffer(p.stdout, dtype=np.int16)))
        return codigo, "ok"

    with ThreadPoolExecutor(max_workers=hilos) as pool:
        for i, (codigo, estado) in enumerate(pool.map(uno, pares.items()), 1):
            print(f"audio {i}/{len(pares)} {codigo} {estado}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="modo", required=True)
    a1 = sub.add_parser("video"); a1.add_argument("video", type=Path); a1.add_argument("--salida", type=Path, required=True)
    a2 = sub.add_parser("lote")
    a2.add_argument("--pares", type=Path, required=True)
    a2.add_argument("--raiz", type=Path, action="append", required=True)
    a2.add_argument("--salida", type=Path, required=True)
    a2.add_argument("--n", type=int, default=200)
    a2.add_argument("--rapido", action="store_true", help="Solo cuadros clave (más rápido, menos fino).")
    a2.add_argument("--hilos", type=int, default=3)
    a3 = sub.add_parser("audio"); a3.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    if a.modo == "audio":
        return rellenar_audio(a.salida)
    if a.modo == "video":
        t0 = time.time(); v = cuadros(a.video); t1 = time.time()
        e = Embebedor(); t2 = time.time(); vec = e(v); t3 = time.time()
        np.save(a.salida, vec)
        print(f"cuadros {v.shape} en {t1 - t0:.1f} s · modelo cargado en {t2 - t1:.1f} s · "
              f"vectores {vec.shape} en {t3 - t2:.2f} s")
    else:
        lote(a.pares, a.raiz, a.salida, a.n, a.rapido, a.hilos)


if __name__ == "__main__":
    main()
