"""Servicio «normas»: ¿el video podría incumplir las normas de Facebook?

Muse Spark 1.3 lee lo que se ve y lo que se dice en todo el video y señala posibles incumplimientos de una lista cerrada
(reglas/normas-facebook-v1.json, cada norma con su fuente pública). Después, en código, se descarta lo que no se sostiene:
norma fuera de la lista, segundo fuera del video o evidencia que no sea copia de los datos. Es una revisión previa, no una
decisión de Meta. Cuesta unos centavos y corre con cada revisión.

Uso:
    python -m retina.normas CARPETA --titulo "..." [--idioma es|en]
"""
from __future__ import annotations

import argparse
import json
import re
from functools import lru_cache
from pathlib import Path

from . import integridad, meta_api
from .esquemas import RAIZ

MODELO = "muse-spark-1.3"
VERSION = "normas-v1"
REGLAS = RAIZ / "reglas" / "normas-facebook-v1.json"
MAX_HALLAZGOS = 5
MIN_PALABRAS_EVIDENCIA = 3
MAX_CARACTERES = 220
IDIOMAS = {"es": "español", "en": "inglés"}


@lru_cache(maxsize=1)
def reglas() -> list[dict]:
    return json.loads(REGLAS.read_text(encoding="utf-8"))["normas"]


def instrucciones() -> str:
    return (RAIZ / "skills" / "normas.md").read_text(encoding="utf-8").split("---", 2)[2].strip()


def _plano(texto: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", integridad.normalizar(texto)).split())


def datos_del_video(carpeta: Path, titulo: str) -> dict:
    man = json.loads((carpeta / "manifiesto.json").read_text(encoding="utf-8"))
    tramos = man["tramos"]
    desc = json.loads((carpeta / "describir.json").read_text(encoding="utf-8"))["tramos"]
    voz = carpeta / "transcribir.json"
    turnos = json.loads(voz.read_text(encoding="utf-8")).get("turnos", []) if voz.exists() else []
    return {"titulo": titulo, "duracion_video_s": man["duracion_s"],
            "se_ve": [{"segundo": round(tramos[d["tramo"]]["inicio_s"]), "que_pasa": d.get("que_pasa", ""),
                       "texto_en_pantalla": d.get("texto_en_pantalla", "")} for d in desc],
            "se_dice": [{"segundo": round(t["startMs"] / 1000), "dice": t["transcript"]} for t in turnos if t.get("transcript")]}


def filtrar(hallazgos: list, datos: dict) -> list[dict]:
    """Lo que se sostiene en los datos. Ante cualquier duda, el hallazgo se descarta: un falso aviso cuesta confianza."""
    validas = {n["id"] for n in reglas()}
    fuente = _plano(json.dumps(datos, ensure_ascii=False))
    salida, vistas = [], set()
    for h in hallazgos:
        if not isinstance(h, dict):
            continue
        norma, segundo = h.get("norma"), h.get("segundo")
        evidencia, por_que = h.get("evidencia"), h.get("por_que")
        if norma not in validas or norma in vistas or not isinstance(evidencia, str) or not isinstance(por_que, str):
            continue
        if not isinstance(segundo, (int, float)) or not 0 <= segundo <= datos["duracion_video_s"]:
            continue
        if not por_que.strip() or len(por_que) > MAX_CARACTERES:
            continue
        cita = _plano(evidencia)
        if len(cita.split()) < MIN_PALABRAS_EVIDENCIA or cita not in fuente:
            continue
        vistas.add(norma)
        salida.append({"norma": norma, "segundo": segundo, "evidencia": evidencia.strip(), "por_que": por_que.strip()})
    return salida[:MAX_HALLAZGOS]


def esquema() -> dict:
    return {"type": "object", "additionalProperties": False, "required": ["hallazgos"], "properties": {"hallazgos": {
        "type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["norma", "segundo", "evidencia", "por_que"],
                                   "properties": {"norma": {"type": "string", "enum": [n["id"] for n in reglas()]},
                                                  "segundo": {"type": "number"}, "evidencia": {"type": "string"},
                                                  "por_que": {"type": "string"}}}}}}


def pedir(datos: dict, idioma: str) -> list:
    lista = [{"id": n["id"], "nombre": n["nombre"], "que_buscar": n["que_buscar"]} for n in reglas()]
    texto = (f"<<<LISTA_DE_NORMAS\n{json.dumps(lista, ensure_ascii=False)}\nLISTA_DE_NORMAS>>>\n\n"
             + meta_api.como_dato("DATOS_DEL_VIDEO", json.dumps({**datos, "idioma_de_la_revision": IDIOMAS[idioma]}, ensure_ascii=False)))
    cuerpo = {"model": MODELO, "reasoning": {"effort": "low"}, "max_output_tokens": 6000, "store": False,
              "text": {"format": {"type": "json_schema", "name": "normas_v1", "strict": True, "schema": esquema()}},
              "input": [{"type": "message", "role": "developer", "content": [{"type": "input_text", "text": instrucciones()}]},
                        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": texto}]}]}
    return json.loads(meta_api.texto_de(meta_api.responder("normas", cuerpo)))["hallazgos"]


def revisar(carpeta: Path, idioma: str = "es", titulo: str = "") -> dict:
    """Se guarda en normas.json. Una vez hecha no se vuelve a pagar."""
    ruta = carpeta / "normas.json"
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))
    datos = datos_del_video(carpeta, titulo)
    por_id = {n["id"]: n for n in reglas()}
    hallazgos = [{**h, "nombre": por_id[h["norma"]]["name" if idioma == "en" else "nombre"], "fuente": por_id[h["norma"]]["fuente"]}
                 for h in filtrar(pedir(datos, idioma), datos)]
    salida = {"version": VERSION, "hallazgos": hallazgos, "revisadas": len(por_id),
              "licencia": {"modelo": MODELO, "instrucciones": f"skills/normas.md ({VERSION})",
                           "reglas": json.loads(REGLAS.read_text(encoding="utf-8"))["version"]}}
    ruta.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    return salida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("carpeta", type=Path)
    ap.add_argument("--titulo", default="")
    ap.add_argument("--idioma", default="es", choices=list(IDIOMAS))
    a = ap.parse_args()
    print(json.dumps(revisar(a.carpeta, a.idioma, a.titulo), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
