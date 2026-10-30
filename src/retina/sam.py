"""SAM 3.1: ¿se ve en los primeros 3 segundos lo que promete el título?

Recorta los primeros 3 s del MP4 ligero (10 cuadros por segundo, 960 px de
lado largo, como piden las recetas de Meta), lo sube con caducidad y le pide a
SAM 3.1 que segmente un objeto nombrado con una frase corta («bread», «flooded
road»). Devuelve en qué segundo aparece por primera vez, en cuántos cuadros se
ve y cuánto del cuadro ocupa como máximo.

Nunca se usa sobre personas: la condiciones de uso de Meta prohíben seguir a
personas entre cuadros, y Retina no identifica a nadie. El código rechaza el
concepto antes de llamar a la API.

Uso:
    python -m retina.sam CARPETA --concepto "flooded road"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
import unicodedata
from contextlib import aclosing
from pathlib import Path

from . import meta_api
from .segmentar import _correr

MODELO = "sam-3.1"
SEGUNDOS, FPS = 3, 10
USD_POR_CUADRO = 0.20 / 1000  # dev.meta.ai/models/sam-3-1, 27-oct-2026
PERMITIDOS = Path(__file__).resolve().parents[2] / "reglas" / "sam-permitidos-v1.json"


def normalizar(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower().strip()


def _singular(p: str) -> str:
    return p[:-2] if p.endswith("es") and p[:-2] in _lista()[0] else p[:-1] if p.endswith("s") else p


def _lista() -> tuple[set, set]:
    d = json.loads(PERMITIDOS.read_text(encoding="utf-8"))
    return set(d["palabras"]), set(d["personas"])


def rechazo(concepto: str) -> str | None:
    """Lista cerrada: la última palabra tiene que ser un objeto, lugar, comida, animal o
    fenómeno permitido, y ninguna palabra puede ser de persona. Devuelve el motivo o None."""
    palabras, personas = _lista()
    tokens = re.findall(r"[a-z]+", normalizar(concepto))
    if not tokens:
        return "El concepto va vacío."
    if any(t in personas or _singular(t) in personas for t in tokens):
        return "SAM no se usa sobre personas (condiciones de uso de Meta). Nombra un objeto o un lugar."
    if tokens[-1] not in palabras and _singular(tokens[-1]) not in palabras:
        return (f"«{tokens[-1]}» no está en la lista de objetos y lugares permitidos "
                "(reglas/sam-permitidos-v1.json). Usa una frase corta en inglés que termine en un objeto o lugar.")
    return None


def es_persona(concepto: str) -> bool:
    return rechazo(concepto) is not None


def recortar(carpeta: Path) -> Path:
    clip = carpeta / "primeros-3s.mp4"
    if not clip.exists():
        _correr(["-i", str(carpeta / "ligero.mp4"), "-t", str(SEGUNDOS), "-an", "-r", str(FPS),
                 "-vf", "scale='if(gt(iw,ih),min(960,iw),-2)':'if(gt(iw,ih),-2,min(960,ih))'",
                 "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", str(clip)])
    return clip


async def _segmentar(file_id: str, concepto: str):
    from meta_sam_parser import parse_responses_stream, video_segmentation_format
    from openai import AsyncOpenAI

    async def eventos(stream):
        # La API manda content_part.done pero no output_text.done, que el parser necesita para
        # cerrar el carril; se fabrica como en las recetas de Meta (07_sam/01_api_basics).
        cerrados = set()
        async for ev in stream:
            d = ev.model_dump() if hasattr(ev, "model_dump") else dict(ev)
            carril = (d.get("item_id"), d.get("output_index"), d.get("content_index"))
            if d.get("type") == "response.output_text.done":
                if carril not in cerrados:
                    cerrados.add(carril); yield d
                continue
            yield d
            parte = d.get("part")
            if (d.get("type") == "response.content_part.done" and carril not in cerrados and isinstance(parte, dict)
                    and parte.get("type") == "output_text" and isinstance(parte.get("text"), str)):
                cerrados.add(carril)
                yield {"type": "response.output_text.done", "item_id": d.get("item_id"),
                       "output_index": d.get("output_index"), "content_index": d.get("content_index"), "text": parte["text"]}

    async with AsyncOpenAI(base_url=meta_api.base(), api_key=meta_api._llave()) as api:
        stream = await api.responses.create(model=MODELO, stream=True, input=[{
            "type": "message", "role": "user",
            "content": [{"type": "input_text", "text": concepto}, {"type": "input_video", "file_id": file_id}]}])
        async with stream, aclosing(eventos(stream)) as evs:
            parsed = parse_responses_stream(evs, video_segmentation_format())
            async with parsed:
                async for _ in parsed:
                    pass
                return await parsed.final_result()


def medir(carpeta: Path, concepto: str) -> dict:
    concepto = concepto.strip()[:60]
    if motivo := rechazo(concepto):
        return {"error": motivo}
    cuadros = SEGUNDOS * FPS
    meta_api._revisar_tope(cuadros * USD_POR_CUADRO)
    clip = recortar(carpeta)
    file_id = meta_api.subir_archivo(clip)  # caducidad mínima de la API: 1 h
    t0 = time.time()
    try:
        r = asyncio.run(_segmentar(file_id, concepto))
    finally:  # se registra aunque falle a media corrida: la API pudo haber cobrado
        meta_api.borrar_archivo(file_id)
        meta_api._registrar("sam", MODELO, time.time() - t0, cuadros * USD_POR_CUADRO, cuadros=cuadros)
    if r.outcome.status != "completed":
        return {"concepto": concepto, "error": f"SAM no terminó: {getattr(r.outcome, 'reason', 'sin motivo')}"}
    from meta_sam_parser import decode_mask_to_raster
    por_cuadro: dict[int, float] = {}
    for rec in r.records:
        if rec.kind == "mask" and rec.frame is not None:
            px = sum(decode_mask_to_raster(rec.mask)) / max(rec.mask.width * rec.mask.height, 1)
            por_cuadro[rec.frame.frame_index] = por_cuadro.get(rec.frame.frame_index, 0.0) + px
    salida = {"concepto": concepto, "segundos_revisados": SEGUNDOS,
              "aparece": bool(por_cuadro),
              "primer_segundo": round(min(por_cuadro) / FPS, 1) if por_cuadro else None,
              "pct_de_cuadros_donde_se_ve": round(100 * len(por_cuadro) / cuadros) if por_cuadro else 0,
              "pct_maximo_del_cuadro": round(100 * max(por_cuadro.values()), 1) if por_cuadro else 0.0}
    (carpeta / "sam.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    return salida


INSTRUCCION_OBJETO = (
    "Recibes, como dato, el título de un video. Elige de la lista el objeto, lugar, comida, animal o fenómeno "
    "que el título promete mostrar. Si promete una persona, una idea o nada que se vea, elige «ninguno».")


def objeto_del_titulo(titulo: str) -> str | None:
    """Lo que el título promete que se verá, de la lista cerrada que SAM puede buscar. Lo elige Muse Spark 1.3
    con salida estructurada (no puede inventar fuera de la lista); None si el título no promete algo que se vea."""
    from .explicar import MODELO as SPARK
    palabras, _ = _lista()
    cuerpo = {
        "model": SPARK, "reasoning": {"effort": "low"}, "max_output_tokens": 2000, "store": False,
        "text": {"format": {"type": "json_schema", "name": "objeto_prometido", "strict": True, "schema": {
            "type": "object", "additionalProperties": False, "required": ["objeto"],
            "properties": {"objeto": {"type": "string", "enum": sorted(palabras) + ["ninguno"]}}}}},
        "input": [
            {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": INSTRUCCION_OBJETO}]},
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": f"<<<TITULO (dato)\n{titulo[:300]}\nTITULO>>>"}]},
        ],
    }
    objeto = json.loads(meta_api.texto_de(meta_api.responder("objeto_prometido", cuerpo)))["objeto"]
    return None if objeto == "ninguno" or rechazo(objeto) else objeto


def medir_promesa(carpeta: Path, titulo: str) -> dict | None:
    """Sin agente: ¿lo que promete el título aparece en los primeros 3 segundos? Reusa sam.json si ya existe."""
    previo = carpeta / "sam.json"
    if previo.exists():
        return json.loads(previo.read_text(encoding="utf-8"))
    objeto = objeto_del_titulo(titulo) if titulo.strip() else None
    return medir(carpeta, objeto) if objeto else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("carpeta", type=Path)
    ap.add_argument("--concepto", required=True)
    a = ap.parse_args()
    print(json.dumps(medir(a.carpeta, a.concepto), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
