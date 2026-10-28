"""Gate 1: una llamada real a Spark desde México y el costo de un video.

Uso:
    python -m retina.gate1 ping
    python -m retina.gate1 video CARPETA_SEGMENTADA

«ping» cuesta fracciones de centavo. «video» sube el MP4 ligero, cuenta los
tokens de entrada (no se cobra), transcribe el audio (≈ 0.005 USD) y borra el
archivo. Lo que mida se copia al BUILD-LOG.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from . import describir, meta_api, transcribir


def ping() -> None:
    t0 = time.time()
    r = meta_api.responder("gate1-ping", {
        "model": "muse-spark-1.3",
        "reasoning": {"effort": "minimal"},
        "max_output_tokens": 200,
        "input": "Responde solo con la palabra: listo",
    })
    print(f"Spark respondió «{meta_api.texto_de(r).strip()}» en {time.time() - t0:.1f} s "
          f"· uso {r.get('usage', {})}")


def video(carpeta: Path) -> None:
    conteo = describir.describir(carpeta, solo_contar=True)
    t = transcribir.transcribir(carpeta)
    print(f"Describir un video: ~{conteo["tokens_entrada_estimados"]:,.0f} tokens de entrada "
          f"≈ {conteo["usd_estimado"]:.3f} USD con salida.")
    print(f"Transcribir: {t['audio_ms'] / 1000:.0f} s de audio, {len(t['turnos'])} turnos.")
    print(f"Gastado en total: {meta_api.gastado_usd():.4f} USD de {meta_api.tope_usd():.0f}.")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "ping":
        ping()
    elif len(sys.argv) >= 3 and sys.argv[1] == "video":
        video(Path(sys.argv[2]))
    else:
        print(__doc__)
