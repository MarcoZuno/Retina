"""Servicio «comparar»: dos versiones del mismo video -> cuál arranca mejor y por qué.

Las cifras de retención de Retina salen de los metadatos (talento, duración, día, título), así
que dos versiones del mismo video reciben casi los mismos números: aquí NO se elige una
ganadora por números. Lo que cambia entre versiones es lo que Retina vio al inicio (gancho,
silencios, texto en pantalla, lo que se dice, las recomendaciones de Meta y la tarjeta de
cada una), y con eso Spark da su opinión de editor sobre cuál arranque es más fuerte.

Solo texto (sirve con Muse Spark Open en Baseten, que no ve video ni tiene modo JSON). Spark
juzga dos veces, en los dos órdenes (A primero y B primero), porque un juez por pares con un
solo orden eligió el segundo video 10 de 10 veces (eval/juez_pares.py). Solo cuenta una
ganadora si los dos órdenes eligen la misma y al menos una diferencia la favorece en los dos;
si no, es empate. De la revisión de Meta solo van las reglas que se revisaron en las dos
versiones (SAM no siempre corre): una regla de más no es algo que el editor cambió. Cada juicio pasa por un
validador en código (valores, cantidades, largos, jerga, cifras que no vienen en los datos y
el filtro de integridad); si falla, se le pide otra vez diciéndole qué, y luego al motor de
rescate. El costo de cada llamada lo anotan meta_api y baseten en costos.jsonl.

Uso:
    python -m retina.comparar CARPETA_A CARPETA_B [--motor abierto+api]
    (escribe CARPETA_B/comparacion.json)
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from . import explicar, integridad, meta_api
from .esquemas import RAIZ

VERSION = "comparacion-v1"
INSTRUCCIONES = "skills/comparar.md (comparar-v2)"
AVISO = "Es la opinión de Spark viendo cómo arranca cada versión, no una predicción de retención medida."
NO_COINCIDEN = ("Spark leyó las dos versiones en los dos órdenes y las dos lecturas no coincidieron: "
                "ninguna arranca claramente mejor. Abajo están las diferencias que vio.")
SIN_SOSTEN = ("En las dos lecturas Spark se inclinó por la versión {}, pero ninguna diferencia se sostuvo en las dos: "
              "tómalo como empate.")
ELECCION = ("primera", "segunda", "empate")
POR_ASPECTO = ("primera", "segunda", "igual")
MAX_POR_QUE, MAX_ASPECTO, MAX_LADO = 220, 60, 140
MIN_DIFERENCIAS, MAX_DIFERENCIAS = 2, 6
# Cifras de retención que salen de los metadatos: en dos versiones del mismo video son casi iguales.
SIN_RETENCION = ("nivel_de_riesgo", "caida_de_videos_parecidos_pp")
TEXTOS_TARJETA = ("por_que", "que_cambiar", "lo_que_funciona")
LISTAS_TARJETA = ("lo_bueno", "lo_flojo", "mejoras_opcionales")  # tarjetas nuevas (29-oct); en las viejas, vacías


def _objeto(p: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "properties": p, "required": list(p)}


def esquema() -> dict:
    texto = {"type": "string"}
    return _objeto({
        "mejor": {"type": "string", "enum": list(ELECCION)},
        "por_que": texto,
        "diferencias": {"type": "array", "items": _objeto({
            "aspecto": texto, "primera": texto, "segunda": texto,
            "mejor": {"type": "string", "enum": list(POR_ASPECTO)}})},
    })


def instrucciones() -> str:
    return (RAIZ / "skills" / "comparar.md").read_text(encoding="utf-8").split("---", 2)[2].strip()


def _resultado(carpeta: Path) -> dict:
    return json.loads((carpeta / "resultado.json").read_text(encoding="utf-8"))


def reglas_meta(carpeta: Path) -> set[str]:
    return {r.get("id", "") for r in _resultado(carpeta).get("revision_meta") or []}


def datos_de_version(carpeta: Path, reglas: set[str] | None = None) -> dict:
    """Lo que Retina ya revisó de una versión: su arranque, la revisión de Meta y su tarjeta.
    Con `reglas`, de la revisión de Meta solo van esas (las que se revisaron en las dos versiones)."""
    resultado = _resultado(carpeta)
    datos = explicar.datos_del_arranque(carpeta, resultado["arranque"])
    for clave in SIN_RETENCION:
        datos.pop(clave, None)
    datos["revision_meta"] = [{"regla": r.get("regla", ""), "cumple": r.get("cumple"), "evidencia": r.get("evidencia", "")}
                              for r in resultado.get("revision_meta") or [] if reglas is None or r.get("id", "") in reglas]
    t = resultado.get("explicacion") or {}
    anzuelo = (t.get("anzuelo_frase") or "") if t.get("anzuelo_detectado", "ninguno") != "ninguno" else ""
    datos["tarjeta"] = {**{k: t.get(k) or "" for k in TEXTOS_TARJETA}, **{k: t.get(k) or [] for k in LISTAS_TARJETA},
                        "anzuelo_frase": anzuelo}
    return datos


def _dicho(datos: dict) -> str:
    """Lo que dicen o muestran las dos versiones (voz, texto en pantalla y el anzuelo que marcó su tarjeta)."""
    partes = []
    for v in datos.values():
        if isinstance(v, dict):
            partes.append(explicar._lo_que_dice_el_video(v))
            partes.append(explicar._sin_signos(str((v.get("tarjeta") or {}).get("anzuelo_frase") or "")))
    return " ".join(partes)


def sin_citas_del_video(texto: str, datos: dict) -> str:
    """Citar entre «comillas» lo que el video ya dice es describirlo, no sugerirlo: esa cita no se filtra."""
    dicho = _dicho(datos)

    def cita(m: re.Match) -> str:
        citado = explicar._sin_signos(m.group(1))
        return "«»" if len(citado) >= 8 and citado in dicho else m.group(0)

    return explicar.CITA.sub(cita, texto)


def revisar(salida, datos: dict) -> list[str]:
    """Problemas de un juicio (vacío si pasa). Nunca truena: lo que no cuadra se le dice a Spark."""
    if not isinstance(salida, dict):
        return ["la respuesta tiene que ser un objeto JSON con «mejor», «por_que» y «diferencias»"]
    problemas, textos = [], []
    if salida.get("mejor") not in ELECCION:
        problemas.append(f"«mejor» «{salida.get('mejor')}» no es un valor válido ({', '.join(ELECCION)})")
    por_que = salida.get("por_que")
    if not isinstance(por_que, str) or not por_que.strip():
        problemas.append("falta «por_que»")
    else:
        textos.append(("«por_que»", por_que))
        if len(por_que) > MAX_POR_QUE:
            problemas.append(f"«por_que» mide {len(por_que)} caracteres; el máximo es {MAX_POR_QUE}")
    difs = salida.get("diferencias")
    if not isinstance(difs, list):
        difs = []
    if not MIN_DIFERENCIAS <= len(difs) <= MAX_DIFERENCIAS:
        problemas.append(f"«diferencias» tiene que traer de {MIN_DIFERENCIAS} a {MAX_DIFERENCIAS} aspectos; trae {len(difs)}")
    for i, d in enumerate(difs, 1):
        if not isinstance(d, dict):
            problemas.append(f"la diferencia {i} no es un objeto con «aspecto», «primera», «segunda» y «mejor»")
            continue
        for campo, tope in (("aspecto", MAX_ASPECTO), ("primera", MAX_LADO), ("segunda", MAX_LADO)):
            v = d.get(campo)
            if not isinstance(v, str) or not v.strip():
                problemas.append(f"la diferencia {i} no trae «{campo}»")
                continue
            textos.append((f"«{campo}» de la diferencia {i}", v))
            if len(v) > tope:
                problemas.append(f"«{campo}» de la diferencia {i} mide {len(v)} caracteres; el máximo es {tope}")
        if d.get("mejor") not in POR_ASPECTO:
            problemas.append(f"«mejor» de la diferencia {i} es «{d.get('mejor')}»; tiene que ser {', '.join(POR_ASPECTO)}")
    if salida.get("mejor") in ("primera", "segunda") and not any(
            isinstance(d, dict) and d.get("mejor") == salida["mejor"] for d in difs):
        problemas.append(f"elegiste la {salida['mejor']} versión pero ninguna diferencia la favorece")
    for nombre, t in textos:
        if j := sorted({m.group(0) for m in explicar.JERGA.finditer(t)}):
            problemas.append(f"{nombre} trae jerga o cifras internas que la persona no debe ver: {', '.join(j)}. "
                             "Di los segundos como «segundo 4» y no cites porcentajes")
    todo = " ".join(t for _, t in textos)
    if n := explicar.cifras_inventadas({"por_que": todo, "lo_que_funciona": "", "que_cambiar": ""}, datos):
        problemas.append(f"cifras que no vienen en los datos: {', '.join(n)}")
    problemas += [f"{r['regla']} (frases: {', '.join(r['frases'])}) — si es algo que el video dice o muestra, "
                  "cítalo entre «comillas» tal como viene en los datos, sin describirlo con otras palabras"
                  for r in integridad.revisar(sin_citas_del_video(todo, datos))]
    return problemas


def _texto_de_datos(datos: dict, aviso: str) -> str:
    texto = "\n\n".join(meta_api.como_dato(f"VERSION_{n}", json.dumps(datos[f"version_{n}"], ensure_ascii=False))
                        for n in (1, 2))
    if aviso:
        texto += f"\n\nTu respuesta anterior fue bloqueada por esto: {aviso}. Corrígelo."
    return texto


def cuerpo(datos: dict, aviso: str = "", esfuerzo: str = "high") -> dict:
    return {
        "model": explicar.MODELO,
        "reasoning": {"effort": esfuerzo},
        "max_output_tokens": 16000,
        "prompt_cache_key": "retina-comparar-v2",  # gitleaks:allow (etiqueta de caché, no es llave)
        "store": False,
        "text": {"format": {"type": "json_schema", "name": "comparacion_v1", "strict": True, "schema": esquema()}},
        "input": [
            {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": instrucciones()}]},
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": _texto_de_datos(datos, aviso)}]},
        ],
    }


FORMATO = ("\n\nFORMATO DE RESPUESTA: devuelve solo un objeto JSON válido, sin texto antes ni después y sin bloques "
           "de código, con exactamente estas claves: «mejor»: uno de primera, segunda, empate; «por_que»: texto; "
           "«diferencias»: lista de objetos, cada uno con exactamente «aspecto» (texto), «primera» (texto), "
           "«segunda» (texto) y «mejor» (uno de primera, segunda, igual).")


def pedir_abierto(datos: dict, aviso: str) -> dict:
    """Muse Spark Open en Baseten: sin modo JSON, el formato va en las instrucciones y el validador revisa."""
    from . import baseten
    mensajes = [{"role": "system", "content": instrucciones() + FORMATO},
                {"role": "user", "content": _texto_de_datos(datos, aviso)}]
    for tope in (8000, 14000):  # a veces gasta la salida pensando y no escribe el JSON: se repite con más espacio
        texto = baseten.chat("comparar", mensajes, esquema(), max_tokens=tope)
        i, f = texto.find("{"), texto.rfind("}")
        if i >= 0 and f > i:
            try:
                return json.loads(texto[i:f + 1])
            except json.JSONDecodeError:
                pass
    raise RuntimeError("Spark Open no devolvió la comparación en JSON.")


def pedir(datos: dict, aviso: str, motor: str = "api") -> dict:
    if motor == "abierto":
        return pedir_abierto(datos, aviso)
    for esfuerzo in ("high", "medium"):  # con razonamiento alto a veces no escribe nada: se repite pensando menos
        texto = meta_api.texto_de(meta_api.responder("comparar", cuerpo(datos, aviso, esfuerzo)))
        if texto.strip():
            return json.loads(texto)
    raise RuntimeError("Spark no devolvió la comparación ni con razonamiento medio.")


def escribir(datos: dict, motores: tuple, pedir=pedir, orden: str = "") -> tuple[dict, list, str]:
    """Pide el juicio a cada motor en orden, dos intentos cada uno, hasta que uno pase el validador.
    Si ninguno pasa, no hay comparación (nada sin validar llega a la persona). El tope de gasto detiene todo."""
    intentos = []
    for motor in motores:
        aviso = ""
        for _ in range(2):
            try:
                s = pedir(datos, aviso, motor)
                problemas = revisar(s, datos)
            except meta_api.TopeAlcanzado:
                raise
            except (RuntimeError, ValueError, TypeError, KeyError, AttributeError) as e:
                intentos.append({"orden": orden, "motor": motor, "mejor": "",
                                 "problemas": [f"respuesta con formato inválido ({type(e).__name__})"]})
                continue
            intentos.append({"orden": orden, "motor": motor, "mejor": str(s.get("mejor", "")), "problemas": problemas})
            if not problemas:
                return s, intentos, motor
            aviso = "; ".join(problemas)
    raise RuntimeError(f"Spark no dio una comparación que pasara el validador (orden {orden}).")


def _a_letras(texto: str, primera: str, segunda: str) -> str:
    """«la versión 1» y «la versión 2» (por orden de llegada) -> «la versión A» o «la versión B»."""
    texto = re.sub(r"\b([Vv]ersiones) 1 y 2\b", rf"\1 {primera} y {segunda}", texto)
    return re.sub(r"\b([Vv]ersi[oó]n) ([12])\b", lambda m: f"{m.group(1)} {primera if m.group(2) == '1' else segunda}", texto)


def mapear(juicio: dict, orden: str) -> dict:
    """Un juicio en «primera»/«segunda» -> en A/B. `orden` es «AB» (A llegó primero) o «BA»."""
    primera, segunda = orden[0], orden[1]
    letra = {"primera": primera, "segunda": segunda, "empate": "empate", "igual": "igual"}
    return {"mejor": letra[juicio["mejor"]], "por_que": _a_letras(juicio["por_que"], primera, segunda),
            "diferencias": [{"aspecto": _a_letras(d["aspecto"], primera, segunda),
                             "a": _a_letras(d["primera" if primera == "A" else "segunda"], primera, segunda),
                             "b": _a_letras(d["segunda" if primera == "A" else "primera"], primera, segunda),
                             "mejor": letra[d["mejor"]]} for d in juicio["diferencias"]]}


def _pareja(d: dict, otras: list[dict]) -> dict | None:
    """El mismo aspecto en el otro orden: mismo nombre, o uno contiene al otro. Sin eso no hay pareja: la posición en
    la lista no dice nada («Encuadre» no es «Voz» por ir en el mismo lugar)."""
    nombre = integridad.normalizar(d["aspecto"]).strip(" .")
    nombres = [integridad.normalizar(o["aspecto"]).strip(" .") for o in otras]
    for k, n in enumerate(nombres):
        if n == nombre:
            return otras[k]
    for k, n in enumerate(nombres):
        if n and nombre and (n in nombre or nombre in n):
            return otras[k]
    return None


def combinar(ab: dict, ba: dict) -> dict:
    """Solo cuenta lo que los dos órdenes dicen igual. El texto sale del orden AB (A llegó primero, como se subió).
    Cada diferencia se busca en el orden BA por el nombre del aspecto; si allá favorece a otra versión o no aparece,
    queda «igual»: así ninguna diferencia depende de qué versión se leyó primero.
    Una ganadora necesita que los dos órdenes la elijan y que al menos una diferencia la sostenga en los dos."""
    diferencias = []
    for d in ab["diferencias"]:
        otra = _pareja(d, ba["diferencias"])
        diferencias.append({**d, "mejor": d["mejor"] if otra is not None and otra["mejor"] == d["mejor"] else "igual"})
    if ab["mejor"] != ba["mejor"]:
        veredicto, por_que = "empate", NO_COINCIDEN
    elif ab["mejor"] != "empate" and not any(d["mejor"] == ab["mejor"] for d in diferencias):
        veredicto, por_que = "empate", SIN_SOSTEN.format(ab["mejor"])
    else:
        veredicto, por_que = ab["mejor"], ab["por_que"]
    return {"veredicto": veredicto,
            "por_que": por_que,
            "diferencias": diferencias,
            "juicios": [{"orden": "AB", "mejor": ab["mejor"], "por_que": ab["por_que"]},
                        {"orden": "BA", "mejor": ba["mejor"], "por_que": ba["por_que"]}]}


def _licencia(quienes: list[str], intentos: list[dict]) -> dict:
    from . import baseten
    servidos = {"abierto": (baseten.MODELO, "Baseten"), "api": (explicar.MODELO, "Meta Model API")}
    usados = list(dict.fromkeys(quienes))
    return {"modelo": " y ".join(servidos[q][0] for q in usados),
            "servido_por": " y ".join(servidos[q][1] for q in usados),
            "instrucciones": INSTRUCCIONES, "intentos": intentos}


def _idioma(carpeta: Path) -> str:
    """El idioma en que se pidió la revisión (lo guarda resultado.json); por omisión, español."""
    try:
        return json.loads((carpeta / "resultado.json").read_text(encoding="utf-8")).get("idioma") or "es"
    except (OSError, ValueError):
        return "es"


def comparar(carpeta_a: Path, carpeta_b: Path, motor: str = "", pedir=pedir) -> dict:
    """Compara el arranque de dos versiones ya revisadas y escribe carpeta_b/comparacion.json."""
    if carpeta_a.resolve() == carpeta_b.resolve():
        raise ValueError("Las dos versiones son la misma carpeta.")
    motor = motor or explicar.motor_por_omision()
    if motor not in explicar.MOTORES:
        raise ValueError(f"El motor tiene que ser uno de {', '.join(explicar.MOTORES)}; dice «{motor}».")
    # Una revisión de Meta que solo se hizo en una versión (SAM corre solo si hay con qué) no es algo que
    # el editor cambió: en el smoke del 29-oct, con el mismo video, esa sola regla inclinó a Spark.
    comunes = reglas_meta(carpeta_a) & reglas_meta(carpeta_b)
    version = {"A": datos_de_version(carpeta_a, comunes), "B": datos_de_version(carpeta_b, comunes)}
    juicios, intentos, quienes = {}, [], []
    for orden in ("AB", "BA"):
        datos = {"version_1": version[orden[0]], "version_2": version[orden[1]]}
        if _idioma(carpeta_b) == "en":
            datos["idioma_de_la_respuesta"] = "inglés"
        salida, i, quien = escribir(datos, explicar.MOTORES[motor], pedir, orden)
        juicios[orden], intentos, quienes = mapear(salida, orden), intentos + i, quienes + [quien]
    resultado = {"version": VERSION, "a": carpeta_a.name, "b": carpeta_b.name,
                 **combinar(juicios["AB"], juicios["BA"]), "aviso": AVISO, "licencia": _licencia(quienes, intentos)}
    temporal = carpeta_b / "comparacion.json.tmp"  # el panel nunca lee un archivo a medias
    temporal.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temporal, carpeta_b / "comparacion.json")
    return resultado


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("carpeta_a", type=Path, help="Carpeta de la revisión de la versión A.")
    ap.add_argument("carpeta_b", type=Path, help="Carpeta de la revisión de la versión B (ahí queda comparacion.json).")
    ap.add_argument("--motor", choices=list(explicar.MOTORES), default="",
                    help="api: Spark 1.3 · abierto: Muse Spark Open en Baseten · abierto+api: Spark Open con rescate "
                         "de Spark 1.3. Por omisión, RETINA_MOTOR del .env.")
    a = ap.parse_args()
    s = comparar(a.carpeta_a, a.carpeta_b, a.motor)
    print(json.dumps({k: s[k] for k in ("veredicto", "por_que", "diferencias", "juicios")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
