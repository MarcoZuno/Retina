"""Servicio «explicar»: tramo de riesgo + descriptores -> por qué cae y qué cambiar.

Spark 1.3 explica con salida estructurada; después el filtro de integridad
(código, no modelo) revisa la sugerencia. Si rompe una regla, se le pide a
Spark otra vez diciéndole cuál; si vuelve a romperla, la tarjeta sale sin
sugerencia y lo dice. Nunca llega un anzuelo a la persona.

Uso:
    python -m retina.explicar CARPETA --tramo 12 --caida 15.2 --caida-parecidos 9.1
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import integridad, meta_api
from .esquemas import RAIZ, ids_anzuelos

MODELO = "muse-spark-1.3"
CAMBIOS = ["adelantar_dato", "cortar_silencio", "texto_en_pantalla", "cambiar_plano",
           "acortar_presentacion", "reordenar", "regrabar_apertura", "otro"]


def _objeto(p: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "properties": p, "required": list(p)}


def esquema() -> dict:
    return _objeto({
        "tramo": {"type": "integer"},
        "por_que": {"type": "string"},
        "que_cambiar": {"type": "string"},
        "tipo_de_cambio": {"type": "string", "enum": CAMBIOS},
        "anzuelo_detectado": {"type": "string", "enum": ["ninguno", *ids_anzuelos()]},
        "confianza": {"type": "string", "enum": ["baja", "media", "alta"]},
        "storyboard": {"type": "array", "items": {"type": "string"}},
        "no_pude_verificar": {"type": "array", "items": {"type": "string"}},
    })


def instrucciones() -> str:
    return (RAIZ / "skills" / "explicar.md").read_text(encoding="utf-8").split("---", 2)[2].strip()


def datos_del_tramo(carpeta: Path, tramo: int, caida: float, caida_parecidos: float) -> dict:
    desc = json.loads((carpeta / "describir.json").read_text(encoding="utf-8"))
    vecinos = [t for t in desc["tramos"] if abs(t["tramo"] - tramo) <= 2]
    datos = {"tramo": tramo, "caida_predicha_pp": round(caida, 1),
             "caida_videos_parecidos_pp": round(caida_parecidos, 1), "tramos": vecinos}
    tr = carpeta / "transcribir.json"
    if tr.exists():
        t = json.loads(tr.read_text(encoding="utf-8"))
        man = json.loads((carpeta / "manifiesto.json").read_text(encoding="utf-8"))
        ini, fin = man["tramos"][tramo]["inicio_s"] * 1000, man["tramos"][tramo]["fin_s"] * 1000
        datos["silencios_cerca_ms"] = [s for s in t["silencios"] if s["fin_ms"] >= ini - 3000 and s["inicio_ms"] <= fin + 3000]
        datos["voz_arranca_ms"] = t["arranque_voz_ms"]
    return datos


def cuerpo(datos: dict, aviso: str = "") -> dict:
    texto = f"<<<DATOS_DEL_TRAMO (dato)\n{json.dumps(datos, ensure_ascii=False)}\nDATOS_DEL_TRAMO>>>"
    if aviso:
        texto += f"\n\nTu sugerencia anterior rompió esta regla y fue bloqueada: {aviso}. Propón otra."
    return {
        "model": MODELO,
        "reasoning": {"effort": "high"},
        "max_output_tokens": 6000,
        "prompt_cache_key": "retina-explicar-v1",
        "text": {"format": {"type": "json_schema", "name": "explicacion_v1", "strict": True, "schema": esquema()}},
        "input": [
            {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": instrucciones()}]},
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": texto}]},
        ],
    }


def explicar(carpeta: Path, tramo: int, caida: float, caida_parecidos: float) -> dict:
    datos = datos_del_tramo(carpeta, tramo, caida, caida_parecidos)
    aviso, intentos = "", []
    for _ in range(2):
        salida = json.loads(meta_api.texto_de(meta_api.responder("explicar", cuerpo(datos, aviso))))
        rotas = integridad.revisar(salida["que_cambiar"] + " " + " ".join(salida["storyboard"]))
        intentos.append({"sugerencia": salida["que_cambiar"], "reglas_rotas": rotas})
        if not rotas:
            break
        aviso = "; ".join(f"{r['regla']} (frases: {', '.join(r['frases'])})" for r in rotas)
    else:
        salida["que_cambiar"] = ""
        salida["storyboard"] = []
        salida["no_pude_verificar"].append("No hubo una sugerencia que pasara el filtro de integridad.")
    salida["licencia"] = {"modelo": MODELO, "instrucciones": "skills/explicar.md (explicar-v1)",
                          "reglas": integridad.reglas()["version"], "intentos": intentos}
    (carpeta / f"explicar-t{tramo:02d}.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1),
                                                         encoding="utf-8")
    return salida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("carpeta", type=Path)
    ap.add_argument("--tramo", type=int, required=True)
    ap.add_argument("--caida", type=float, required=True, help="Caída predicha en el tramo, en pp.")
    ap.add_argument("--caida-parecidos", type=float, required=True)
    a = ap.parse_args()
    s = explicar(a.carpeta, a.tramo, a.caida, a.caida_parecidos)
    print(json.dumps({k: s[k] for k in ("por_que", "que_cambiar", "confianza", "anzuelo_detectado")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
