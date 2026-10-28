"""Servicio «explicar»: riesgo del arranque + lo que se ve y se oye -> por qué y qué cambiar.

El nivel (alto, medio, bajo) lo calcula el código (retina.arranque); Spark 1.3
solo interpreta qué del gancho y del primer cuarto lo explica. Después, en
código, un validador revisa que las cifras salgan de los datos y que el
momento caiga dentro del arranque, y el filtro de integridad revisa la
sugerencia. Si algo falla, se le pide a Spark otra vez diciéndole qué; si
vuelve a fallar, la tarjeta sale sin sugerencia y lo dice. Nunca llega un
anzuelo a la persona.

Uso:
    python -m retina.explicar CARPETA      (lee el «arranque» de CARPETA/resultado.json)
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from . import integridad, meta_api
from .esquemas import RAIZ, ids_anzuelos
from .voz import BLOQUES

MODELO = "muse-spark-1.3"
CAMBIOS = ["ninguno", "adelantar_dato", "cortar_silencio", "texto_en_pantalla", "cambiar_plano",
           "acortar_presentacion", "reordenar", "regrabar_apertura", "otro"]
FIN_ARRANQUE = BLOQUES[1][1]  # tramos 0-9: gancho + primer cuarto
CAMPOS_TRAMO = ("que_pasa", "texto_en_pantalla", "tipo_de_plano", "cambio_de_plano",
                "presentador_en_pantalla", "tipo_de_gancho")
MAX_CARACTERES = 220  # por campo de texto: la tarjeta se lee de un vistazo
# Lo que la persona no tiene por qué entender: jerga del sistema y cifras internas de audiencia.
JERGA = re.compile(r"\bpp\b|puntos porcentuales|%|de cada 100|\bs\d+(?:[.,]\d+)?\b|\btramos?\b|"
                   r"ver_arranque|ver_tramos|\boir\b|buscar_parecidos|medir_lo_prometido|entregar_tarjeta|"
                   r"momento_s|\w+_\w+", re.I)
INTOCABLES = RAIZ / "reglas" / "intocables-v1.json"


def _objeto(p: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "properties": p, "required": list(p)}


def esquema() -> dict:
    return _objeto({
        "por_que": {"type": "string"},
        "lo_que_funciona": {"type": "string"},
        "que_cambiar": {"type": "string"},
        "tipo_de_cambio": {"type": "string", "enum": CAMBIOS},
        "momento_s": {"type": "number"},
        "anzuelo_detectado": {"type": "string", "enum": ["ninguno", *ids_anzuelos()]},
        "anzuelo_frase": {"type": "string"},
        "anzuelo_momento_s": {"type": "number"},
        "confianza": {"type": "string", "enum": ["baja", "media", "alta"]},
        "storyboard": {"type": "array", "items": {"type": "string"}},
        "no_pude_verificar": {"type": "array", "items": {"type": "string"}},
    })


def instrucciones() -> str:
    return (RAIZ / "skills" / "explicar.md").read_text(encoding="utf-8").split("---", 2)[2].strip()


def datos_del_arranque(carpeta: Path, arranque: dict) -> dict:
    man = json.loads((carpeta / "manifiesto.json").read_text(encoding="utf-8"))
    desc = json.loads((carpeta / "describir.json").read_text(encoding="utf-8"))
    t = man["tramos"]
    fin_s = t[FIN_ARRANQUE - 1]["fin_s"]
    gancho, cuarto = arranque["bloques"][:2]
    datos = {
        "duracion_video_s": man["duracion_s"],
        "gancho_s": [0, round(t[BLOQUES[0][1] - 1]["fin_s"], 1)],
        "primer_cuarto_s": [round(t[BLOQUES[1][0]]["inicio_s"], 1), round(fin_s, 1)],
        "nivel_de_riesgo": arranque["nivel"],
        # Contexto para el modelo, nunca para la tarjeta: el validador no deja citar porcentajes.
        "caida_de_videos_parecidos_pp": {"gancho": gancho["caida_parecidos_pp"],
                                         "primer_cuarto": cuarto["caida_parecidos_pp"]},
        "tramos": [{"inicio_s": round(t[d["tramo"]]["inicio_s"], 1), "fin_s": round(t[d["tramo"]]["fin_s"], 1),
                    **{k: d[k] for k in CAMPOS_TRAMO}}
                   for d in desc["tramos"] if d["tramo"] < FIN_ARRANQUE],
    }
    tr = carpeta / "transcribir.json"
    if tr.exists():
        x = json.loads(tr.read_text(encoding="utf-8"))
        datos["voz_arranca_s"] = None if x["arranque_voz_ms"] is None else round(x["arranque_voz_ms"] / 1000, 1)
        datos["frases"] = [{"segundo": round(f["startMs"] / 1000, 1), "dice": f["transcript"]}
                           for f in x["turnos"] if f["startMs"] < fin_s * 1000]
        datos["silencios_s"] = [[round(s["inicio_ms"] / 1000, 1), round(s["fin_ms"] / 1000, 1)]
                                for s in x["silencios"] if s["inicio_ms"] < fin_s * 1000]
    return datos


_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def cifras_inventadas(salida: dict, datos: dict) -> list[str]:
    """Números del texto que no salen de los datos (se acepta el redondeo a entero)."""
    en_datos = {float(n.replace(",", ".")) for n in _NUM.findall(json.dumps(datos, ensure_ascii=False))}
    validos = en_datos | {float(round(x)) for x in en_datos} | {float(int(x)) for x in en_datos} | {0.0, 1.0, 2.0, 3.0}
    texto = " ".join([salida["por_que"], salida["lo_que_funciona"], salida["que_cambiar"]])
    return sorted({n for n in _NUM.findall(texto) if float(n.replace(",", ".")) not in validos})


QUITAR = re.compile(r"\b(quit\w*|elimin\w*|cort\w*|borr\w*|sac\w*)\b[^«\"]{0,30}[«\"][^»\"]*[»\"]", re.I)


def sin_citas_a_quitar(texto: str) -> str:
    """«Quita "comparte con tu familia"» cita el anzuelo para quitarlo: esa cita no es la sugerencia."""
    return QUITAR.sub(lambda m: m.group(1), texto)


def toca_intocable(texto: str) -> list[str]:
    """Elementos de marca, ley o línea editorial que la sugerencia quiere quitar o cambiar."""
    reglas = json.loads(INTOCABLES.read_text(encoding="utf-8"))
    t = integridad.normalizar(texto)

    def patron(f: str) -> str:
        return rf"\b{re.escape(integridad.normalizar(f).rstrip('*'))}{r'\w*' if f.endswith('*') else ''}"

    verbos = [m.start() for v in reglas["verbos"] for m in re.finditer(patron(v), t)]
    tocados = []
    for e in reglas["elementos"]:
        lugares = [m.start() for f in e["frases"] for m in re.finditer(patron(f), t)]
        if any(abs(a - b) <= 60 for a in lugares for b in verbos):
            tocados.append(e["nombre"])
    return tocados


def revisar(salida: dict, datos: dict) -> list[str]:
    problemas = []
    for campo, opciones in (("tipo_de_cambio", CAMBIOS), ("anzuelo_detectado", ["ninguno", *ids_anzuelos()]),
                            ("confianza", ["baja", "media", "alta"])):
        if salida.get(campo) not in opciones:  # el agente no tiene esquema estricto: se revisa aquí
            problemas.append(f"{campo} «{salida.get(campo)}» no es un valor válido ({', '.join(opciones)})")
    texto = " ".join([sin_citas_a_quitar(salida["que_cambiar"]), salida["lo_que_funciona"], *salida["storyboard"]])
    problemas += [f"{r['regla']} (frases: {', '.join(r['frases'])})" for r in integridad.revisar(texto)]
    if t := toca_intocable(salida["que_cambiar"]):
        problemas.append(f"la sugerencia toca algo intocable: {', '.join(t)}")
    for campo in ("por_que", "lo_que_funciona", "que_cambiar"):
        if j := sorted({m.group(0) for m in JERGA.finditer(salida[campo])}):
            problemas.append(f"«{campo}» trae jerga o cifras internas que la persona no debe ver: {', '.join(j)}. "
                             "Di los segundos como «segundo 4» y no cites porcentajes")
        if len(salida[campo]) > MAX_CARACTERES:
            problemas.append(f"«{campo}» mide {len(salida[campo])} caracteres; el máximo es {MAX_CARACTERES}")
    if salida["anzuelo_detectado"] != "ninguno":
        if not salida.get("anzuelo_frase", "").strip():
            problemas.append("marcaste un anzuelo pero no dijiste cuál frase o qué se ve en «anzuelo_frase»")
        if not salida["que_cambiar"].strip():
            problemas.append("el video trae un anzuelo: «que_cambiar» tiene que decir cómo quitarlo")
        if not 0 <= salida.get("anzuelo_momento_s", -1) <= datos["duracion_video_s"]:
            problemas.append("«anzuelo_momento_s» tiene que ser el segundo del video donde aparece el anzuelo")
    if n := cifras_inventadas(salida, datos):
        problemas.append(f"cifras que no vienen en los datos: {', '.join(n)}")
    if not 0 <= salida["momento_s"] <= datos["primer_cuarto_s"][1]:
        problemas.append(f"momento_s {salida['momento_s']} fuera del arranque (0 a {datos['primer_cuarto_s'][1]} s)")
    if datos["nivel_de_riesgo"] != "bajo" and not salida["que_cambiar"].strip() and salida["anzuelo_detectado"] == "ninguno":
        problemas.append("el nivel no es «bajo» y no trae un cambio")
    return problemas


def cuerpo(datos: dict, aviso: str = "", esfuerzo: str = "high") -> dict:
    texto = f"<<<DATOS_DEL_ARRANQUE (dato)\n{json.dumps(datos, ensure_ascii=False)}\nDATOS_DEL_ARRANQUE>>>"
    if aviso:
        texto += f"\n\nTu respuesta anterior fue bloqueada por esto: {aviso}. Corrígelo."
    return {
        "model": MODELO,
        "reasoning": {"effort": esfuerzo},
        "max_output_tokens": 16000,
        "prompt_cache_key": "retina-explicar-v3",  # gitleaks:allow (etiqueta de caché, no es llave)
        "store": False,
        "text": {"format": {"type": "json_schema", "name": "explicacion_v3", "strict": True, "schema": esquema()}},
        "input": [
            {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": instrucciones()}]},
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": texto}]},
        ],
    }


def pedir(datos: dict, aviso: str) -> dict:
    """Con razonamiento alto, Spark a veces gasta toda la salida pensando y no escribe nada
    (medido el 27-oct: 5,998 de 6,000 tokens). Si llega vacía, se repite pensando menos."""
    for esfuerzo in ("high", "medium"):
        texto = meta_api.texto_de(meta_api.responder("explicar", cuerpo(datos, aviso, esfuerzo)))
        if texto.strip():
            return json.loads(texto)
    raise RuntimeError("Spark no devolvió la explicación ni con razonamiento medio.")


def explicar(carpeta: Path, arranque: dict) -> dict:
    datos = datos_del_arranque(carpeta, arranque)
    aviso, intentos = "", []
    for _ in range(2):
        salida = pedir(datos, aviso)
        problemas = revisar(salida, datos)
        intentos.append({"sugerencia": salida["que_cambiar"], "problemas": problemas})
        if not problemas:
            break
        aviso = "; ".join(problemas)
    else:
        salida.update(que_cambiar="", tipo_de_cambio="ninguno", storyboard=[])
        salida["no_pude_verificar"].append("No hubo una sugerencia que pasara el validador y el filtro de integridad.")
    salida["licencia"] = {"modelo": MODELO, "instrucciones": "skills/explicar.md (explicar-v3)",
                          "reglas": integridad.reglas()["version"], "intentos": intentos}
    (carpeta / "explicar.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    return salida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("carpeta", type=Path)
    a = ap.parse_args()
    arranque = json.loads((a.carpeta / "resultado.json").read_text(encoding="utf-8"))["arranque"]
    s = explicar(a.carpeta, arranque)
    print(json.dumps({k: s[k] for k in ("por_que", "que_cambiar", "momento_s", "confianza", "anzuelo_detectado")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
