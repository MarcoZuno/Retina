"""Servicio «transcribir»: WAV -> turnos de habla con tiempo (Voice Transcribe).

De los turnos salen los silencios y en qué segundo arranca la voz; Spark no
oye bien el audio dentro del MP4, así que el audio solo pasa por aquí.

Uso:
    python -m retina.transcribir CARPETA
"""
from __future__ import annotations

import argparse
import json
import re
import wave
from pathlib import Path

from . import meta_api

# Voice Transcribe acepta hasta unos 10 minutos de audio (32 MB). Para el arranque basta: lo de después se
# recorta y la tarjeta dice hasta dónde se escuchó.
ESCUCHA_MAXIMA_S = 10 * 60
# Palabras de todos los días que delatan el idioma. Retina aprendió con videos en español.
COMUNES = {
    "pt": set("de que o a e do da em um uma para é com não os no se na por mais as dos como mas foi ao ele das tem à seu sua "
              "ou ser quando muito há nos já está eu também só pelo pela até isso ela entre era depois sem mesmo aos ter "
              "seus quem nas me esse eles estão você tinha foram essa num nem suas meu às minha têm numa pelos elas havia "
              "seja qual será nós tenho lhe deles essas esses pelas este fosse dele tu te vocês vos lhes meus minhas teu "
              "tua teus tuas nosso nossa nossos nossas dela delas esta estes estas aquele aquela aqueles aquelas isto aquilo "
              "obrigado obrigada aqui vamos fazer".split()),
    "fr": set("le la les de des du un une et est en que qui dans pour pas sur au avec ce il elle je tu nous vous ils elles "
              "se ne plus par mais ou où son sa ses leur leurs cette ces mon ma mes ton ta tes très tout tous être avoir "
              "fait faire aussi comme bien sans sous ça c'est j'ai qu'il d'un d'une l'on y a été sont était dit peut "
              "même alors encore merci voici voilà quand si donc car cela cet ceux celui".split()),
    "es": set("de la que el en y los se del las un por con no una su para es al lo como más pero sus le ya "
              "este sí porque esta cuando muy sin sobre también me hasta hay donde todo nos uno les ni eso esto "
              "qué yo otro él ella mi tu te así cómo hoy vas aquí mira".split()),
    "en": set("the of and to in is it you that was for on are with as they be at have this from or had by not "
              "but what all were we when your can there an which she do how their if will up about out then them "
              "so would like him into has look more go see could people my than who its now did get here watch".split()),
}


MARGEN = 1.5  # el idioma que gana tiene que sacarle esta ventaja al segundo: «de», «que» y «para» son de varios a la vez
PROPORCION = 0.12  # y sus palabras comunes tienen que ser al menos esta parte del texto


def idioma_detectado(texto: str) -> str | None:
    """«es», «en», «pt» o «fr» si el texto lo deja claro: dos palabras comunes o más, con ventaja sobre el segundo idioma
    y una parte razonable del texto. Un portugués no se confunde con español solo porque comparten palabras."""
    palabras = re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", (texto or "").lower())
    cuenta = {k: sum(p in comunes for p in palabras) for k, comunes in COMUNES.items()}
    orden = sorted(cuenta, key=cuenta.get, reverse=True)
    gana, segundo = orden[0], orden[1]
    if cuenta[gana] >= 2 and cuenta[gana] >= MARGEN * cuenta[segundo] and cuenta[gana] > cuenta[segundo] \
            and cuenta[gana] >= PROPORCION * len(palabras):
        return gana
    return None


def idioma_de(texto: str) -> str | None:
    """Solo «es» o «en» (los idiomas de la tarjeta y de la apertura); un portugués o un francés no es ninguno de los dos."""
    lengua = idioma_detectado(texto)
    return lengua if lengua in ("es", "en") else None


def recortar(wav: Path, segundos: float = ESCUCHA_MAXIMA_S) -> tuple[Path, float | None]:
    """El WAV tal cual si cabe; si no, una copia con sus primeros `segundos` y hasta dónde llega."""
    with wave.open(str(wav), "rb") as w:
        if w.getnframes() <= segundos * w.getframerate():
            return wav, None
        corto = wav.with_name(f"{wav.stem}-primeros-{int(segundos // 60)}-min.wav")
        with wave.open(str(corto), "wb") as c:
            c.setparams(w.getparams())
            c.writeframes(w.readframes(int(segundos * w.getframerate())))
    return corto, float(segundos)


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


def transcribir(carpeta: Path, lengua: str | None = None, idioma_panel: str = "es") -> dict:
    """`lengua`: «en» o «es» si el título lo deja claro. Si no (None: «Sourdough Bread Recipe»), no se supone español:
    se le dejan los dos idiomas al servicio, con primero el que la persona usa en el panel."""
    manifiesto = json.loads((carpeta / "manifiesto.json").read_text(encoding="utf-8"))
    if not manifiesto.get("audio"):
        raise ValueError("El video no trae audio.")
    wav, hasta_s = recortar(carpeta / manifiesto["audio"])
    por_idioma = {"en": ("English",), "es": ("Spanish",)}
    idiomas = por_idioma.get(lengua) or (("English", "Spanish") if idioma_panel == "en" else ("Spanish", "English"))
    datos = meta_api.transcribir_wav(wav, idiomas=idiomas)
    turnos = datos.get("turns", [])
    dur_ms = datos.get("audioDurationMs") or int(manifiesto["duracion_s"] * 1000)
    salida = {
        "version": "transcribir-v1",
        "audio_ms": dur_ms,
        "arranque_voz_ms": turnos[0]["startMs"] if turnos else None,
        "turnos": [{k: t.get(k) for k in ("turnId", "startMs", "endMs", "transcript")} for t in turnos],
        "silencios": silencios(turnos, dur_ms),
        "escucho_hasta_s": hasta_s,  # None: se escuchó completo
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
