"""Servicio «transcribir»: WAV -> turnos de habla con tiempo (Voice Transcribe).

De los turnos salen los silencios y en qué segundo arranca la voz; Spark no
oye bien el audio dentro del MP4, así que el audio solo pasa por aquí.

Uso:
    python -m retina.transcribir CARPETA
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import meta_api


def silencios(turnos: list[dict], duracion_ms: int, minimo_ms: int = 3000) -> list[dict]:
    """Huecos sin voz de al menos `minimo_ms`, incluidos el inicio y el final."""
    huecos, cursor = [], 0
    for t in sorted(turnos, key=lambda t: t["startMs"]):
        if t["startMs"] - cursor >= minimo_ms:
            huecos.append({"inicio_ms": cursor, "fin_ms": t["startMs"]})
        cursor = max(cursor, t["endMs"])
    if duracion_ms - cursor >= minimo_ms:
        huecos.append({"inicio_ms": cursor, "fin_ms": duracion_ms})
    return huecos


def transcribir(carpeta: Path) -> dict:
    manifiesto = json.loads((carpeta / "manifiesto.json").read_text(encoding="utf-8"))
    datos = meta_api.transcribir_wav(carpeta / manifiesto["audio"])
    turnos = datos.get("turns", [])
    dur_ms = datos.get("audioDurationMs") or int(manifiesto["duracion_s"] * 1000)
    salida = {
        "version": "transcribir-v1",
        "audio_ms": dur_ms,
        "arranque_voz_ms": turnos[0]["startMs"] if turnos else None,
        "turnos": [{k: t.get(k) for k in ("turnId", "startMs", "endMs", "transcript")} for t in turnos],
        "silencios": silencios(turnos, dur_ms),
        "licencia": {"modelo": "muse-voice-transcribe-1.0", "modo": "ENDPOINTING",
                     "nota": "Tiempos por turno, no por palabra."},
    }
    (carpeta / "transcribir.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    return salida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("carpeta", type=Path)
    s = transcribir(ap.parse_args().carpeta)
    print(f"{len(s['turnos'])} turnos · voz desde {s['arranque_voz_ms']} ms · "
          f"{len(s['silencios'])} silencios de 3 s o más")


if __name__ == "__main__":
    main()
