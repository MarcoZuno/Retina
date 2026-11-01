"""Servicio «explicar»: riesgo del arranque + lo que se ve y se oye -> por qué y qué cambiar.

El nivel (alto, medio, bajo) lo calcula el código (retina.arranque); Spark 1.3
solo interpreta qué del gancho y del primer cuarto lo explica. Después, en
código, un validador revisa que las cifras salgan de los datos y que el
momento caiga dentro del arranque, y el filtro de integridad revisa la
sugerencia. Si algo falla, se le pide a Spark otra vez diciéndole qué; si
vuelve a fallar, la tarjeta sale vacía (ningún texto del modelo) y lo dice. Nunca llega un
anzuelo a la persona.

Uso:
    python -m retina.explicar CARPETA      (lee el «arranque» de CARPETA/resultado.json)
"""
from __future__ import annotations

import argparse
import json
import os
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
MAX_PASOS, MAX_CARACTERES_PASO = 4, 140  # «qué hacer» en pasos que un editor sigue sin explicación
# Lo bueno, lo flojo y mejoras opcionales (29-oct): la tarjeta verde casi no decía nada a quien edita.
# (mínimo, máximo, caracteres por punto). Las mejoras miden lo mismo que un paso: se hacen en el editor.
LISTAS = {"lo_bueno": (1, 3, 160), "lo_flojo": (0, 3, 160), "mejoras_opcionales": (0, 3, MAX_CARACTERES_PASO),
          "no_pude_verificar": (0, 3, 160)}  # el panel también lo muestra
NUM_LETRA = (r"(?:cien\w*|mil|diez|once|doce|trece|catorce|quince|veinte|veinti\w+|treinta|cuarenta|cincuenta|sesenta|"
             r"setenta|ochenta|noventa|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|\d+)")
NUM_LETRA_EN = (r"(?:hundred|thousand|ten|twelve|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|two|three|four|"
                r"five|six|seven|eight|nine)")
# Lo que la persona no tiene por qué entender: jerga del sistema y cifras internas de audiencia.
JERGA = re.compile(r"\bpp\b|puntos porcentuales|%|de cada 100|\bs\d+(?:[.,]\d+)?\b|\btramos?\b|"
                   r"ver_arranque|ver_tramos|\boir\b|buscar_parecidos|medir_lo_prometido|entregar_tarjeta|"
                   r"momento_s|\w+_\w+|"
                   # Cifras escritas con letra: «doce por ciento», «twelve percent», «de cada cien», «out of 100».
                   r"por\s*ciento|porciento|\bper\s*cent|\bpercent\b|\bpor\s+cada\s+cien\w*|\ben\s+cada\s+cien\w*|"
                   rf"\bde\s+cada\s+{NUM_LETRA}\b|\bout\s+of\s+(?:every\s+|each\s+|a\s+|one\s+)?(?:\d+|{NUM_LETRA_EN})\b|"
                   r"\bper\s+hundred\b", re.I)
INTOCABLES = RAIZ / "reglas" / "intocables-v1.json"


# Un enlace, un correo o un dominio con ruta: lo que escribe el modelo para la persona nunca los lleva.
ENLACE = re.compile(r"https?://|\bwww\.|[\w.+-]+@[\w-]+\.[a-z]{2,}|\b[a-z0-9-]+\.[a-z]{2,}/\S|"
                    r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|mx|io|co|me|ly|tv|app|xyz|info|biz|ws|link|shop|store|site|online|us|ai|gg|click|top|live|vip|icu|cc|tk|pw|cam|lol|dev|page|club|sbs|cfd|mobi|pro)\b",
                    re.I)


def enlaces(texto: str) -> list[str]:
    return sorted({m.group(0).lower() for m in ENLACE.finditer(texto)})


def _objeto(p: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "properties": p, "required": list(p)}


def esquema() -> dict:
    return _objeto({
        "por_que": {"type": "string"},
        "lo_que_funciona": {"type": "string"},
        "lo_bueno": {"type": "array", "items": {"type": "string"}},
        "lo_flojo": {"type": "array", "items": {"type": "string"}},
        "que_cambiar": {"type": "string"},
        "pasos": {"type": "array", "items": {"type": "string"}},
        "mejoras_opcionales": {"type": "array", "items": {"type": "string"}},
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
    datos = {
        "duracion_video_s": man["duracion_s"],
        "gancho_s": [0, round(t[BLOQUES[0][1] - 1]["fin_s"], 1)],
        "primer_cuarto_s": [round(t[BLOQUES[1][0]]["inicio_s"], 1), round(fin_s, 1)],
        "nivel_de_riesgo": arranque["nivel"],
        "tramos": [{"inicio_s": round(t[d["tramo"]]["inicio_s"], 1), "fin_s": round(t[d["tramo"]]["fin_s"], 1),
                    **{k: d[k] for k in CAMPOS_TRAMO}}
                   for d in desc["tramos"] if d["tramo"] < FIN_ARRANQUE],
    }
    if len(arranque.get("bloques") or []) >= 2:
        gancho, cuarto = arranque["bloques"][:2]
        # Contexto para el modelo, nunca para la tarjeta: el validador no deja citar porcentajes.
        datos["caida_de_videos_parecidos_pp"] = {"gancho": gancho["caida_parecidos_pp"],
                                                 "primer_cuarto": cuarto["caida_parecidos_pp"]}
    sam = carpeta / "sam.json"
    if sam.exists():  # lo midió SAM 3.1 sobre los primeros 3 segundos
        x = json.loads(sam.read_text(encoding="utf-8"))
        if "aparece" in x:
            datos["lo_que_promete_el_titulo"] = {"objeto": x["concepto"], "se_ve_en_los_primeros_3_s": x["aparece"],
                                                 "desde_el_segundo": x["primer_segundo"]}
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


def lista(salida: dict, campo: str) -> list[str]:
    """Una lista de textos de la tarjeta. Las tarjetas de antes del 29-oct no traen lo_bueno, lo_flojo ni
    mejoras_opcionales: lo que falta, o no es lista de textos, cuenta como lista vacía."""
    v = salida.get(campo)
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def cifras_inventadas(salida: dict, datos: dict) -> list[str]:
    """Números del texto que no salen de los datos (se acepta el redondeo a entero)."""
    en_datos = {float(n.replace(",", ".")) for n in _NUM.findall(json.dumps(datos, ensure_ascii=False))}
    validos = en_datos | {float(round(x)) for x in en_datos} | {float(int(x)) for x in en_datos} | {0.0, 1.0, 2.0, 3.0}
    texto = " ".join([salida["por_que"], salida["lo_que_funciona"], salida["que_cambiar"], *lista(salida, "pasos"),
                      *(t for campo in LISTAS for t in lista(salida, campo))])
    return sorted({n for n in _NUM.findall(texto) if float(n.replace(",", ".")) not in validos})


# También los verbos de señalar: «ubica la frase «…»» es el paso previo a cortarla, no una sugerencia de decirla.
QUITAR = re.compile(r"\b(?:quit|elimin|cort|borr|sac|reemplaz|sustitu|remov|delet|cut|drop|trim|replac|swap|erase|"
                    r"ubic|localiz|busc|encuentr|identific|locat|find|spot)\w*", re.I)
# Entre el verbo de quitar y la cita no puede haber otra orden: «corta el silencio y repite «…»».
# También cuenta lo que se propone poner: «reemplaza el saludo por «…»», «replace the greeting with «…»».
OTRA_ORDEN = re.compile(r"\b(?:di|dilo|dile|diles|pon|ponlo|ponla|ponle|agrega|añade|anade|repite|mantén|manten|deja|"
                        r"adelanta|mueve|pasa|sube|usa|pide|invita|cierra|termina|escribe|graba|por|con|cambia|"
                        r"cámbialo|cambialo|sustituye|reemplaza|reemplázalo|muestra|incluye|inserta|lee|menciona|"
                        r"empieza|comienza|coloca|diga|digan|diciendo|"
                        r"say|add|write|put|type|insert|include|use|replace|with|by|to|ask|tell|invite|read|show|"
                        r"display|mention|start|end|repeat|keep|change|swap|substitute|caption|label)\b", re.I)
# «donde empieza «…»» señala un lugar del video; no es la orden de empezar con eso.
SENALA_LUGAR = re.compile(r"\b(?:donde|cuando|where|when)\s+(?:empieza|comienza|termina|it\s+starts|it\s+ends|starts|ends)\b", re.I)
CITA = re.compile(r"[«\"“‘']([^«»\"“”‘’']+)[»\"”’']")
FIN_DE_FRASE = re.compile(r"[.!?;](?=\s|$)")  # no corta en «4.9»


def _sin_signos(texto: str) -> str:
    t = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", integridad.normalizar(texto))).strip()
    return re.sub(r"\b(\w+)(?: \1\b)+", r"\1", t)  # la transcripción repite al tartamudear: «perritos perritos»


def _lo_que_dice_el_video(datos: dict) -> str:
    partes = [str(f.get("dice") or "") for f in datos.get("frases", [])]
    partes += [str(t.get("texto_en_pantalla") or "") for t in datos.get("tramos", []) if isinstance(t, dict)]
    return _sin_signos(" ".join(partes))


def _fuente(datos: dict) -> str:
    """Todo lo que el video dice o muestra, normalizado: de ahí tiene que salir lo que la tarjeta cita como anzuelo."""
    partes = [_lo_que_dice_el_video(datos)]
    partes += [_sin_signos(str(t.get("que_pasa") or "")) for t in datos.get("tramos", []) if isinstance(t, dict)]
    return " ".join(partes)


def sin_citas_a_quitar(texto: str, datos: dict | None = None) -> str:
    """«Corta “Comparte esta información…”» cita el anzuelo para quitarlo: esa cita no es la sugerencia.
    Cuenta si el verbo de quitar va justo antes, o más lejos en la misma frase si lo citado es lo que
    el video ya dice (transcripción o texto en pantalla). Con otra orden en medio, la cita se revisa."""
    dicho = _lo_que_dice_el_video(datos or {})

    def cita(m: re.Match) -> str:
        antes = texto[:m.start()]
        cortes = list(FIN_DE_FRASE.finditer(antes))
        frase = antes[cortes[-1].end():] if cortes else antes
        verbos = list(QUITAR.finditer(frase))
        if not verbos or OTRA_ORDEN.search(SENALA_LUGAR.sub(" ", entre := frase[verbos[-1].end():])):
            return m.group(0)
        citado = _sin_signos(m.group(1))
        return "«»" if len(entre) <= 30 or (len(citado) >= 8 and citado in dicho) else m.group(0)

    return CITA.sub(cita, texto)


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
    pasos = salida.get("pasos", [])
    bueno, mejoras, sin_verificar = lista(salida, "lo_bueno"), lista(salida, "mejoras_opcionales"), lista(salida, "no_pude_verificar")
    # «lo_flojo» puede nombrar el anzuelo que ya trae el video, como «por_que»; lo bueno y las mejoras, nunca.
    texto = " ".join(sin_citas_a_quitar(t, datos) for t in [salida["que_cambiar"], salida["lo_que_funciona"],
                                                             *salida["storyboard"], *pasos, *bueno, *mejoras, *sin_verificar])
    cita = (" — si es el anzuelo que hay que quitar, cítalo entre «comillas» tal como se dice en el video, "
            "sin describirlo con otras palabras") if salida.get("anzuelo_detectado", "ninguno") != "ninguno" else ""
    campos = {"que_cambiar": [salida["que_cambiar"]], "lo_que_funciona": [salida["lo_que_funciona"]], "storyboard": salida["storyboard"],
              "pasos": pasos, "lo_bueno": bueno, "mejoras_opcionales": mejoras, "no_pude_verificar": sin_verificar}
    for r in integridad.revisar(texto):  # se dice en qué campo: sin eso, el modelo corrige el que no es
        donde = [c for c, v in campos.items() if any(integridad.revisar(sin_citas_a_quitar(t, datos)) for t in v)]
        problemas.append(f"{r['regla']} (frases: {', '.join(r['frases'])}; en {', '.join(donde)}){cita}")
    if t := toca_intocable(" ".join([salida["que_cambiar"], *pasos])):
        problemas.append(f"la sugerencia toca algo intocable: {', '.join(t)}")
    for i, m in enumerate(mejoras, 1):  # una por una: cada mejora es un cambio aparte
        if t := toca_intocable(m):
            problemas.append(f"la mejora opcional {i} toca algo intocable: {', '.join(t)}")
    for campo, (minimo, maximo, caracteres) in LISTAS.items():
        v = salida.get(campo, [])
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            problemas.append(f"«{campo}» tiene que ser una lista de textos")
            continue
        if not minimo <= len(v) <= maximo:
            problemas.append(f"«{campo}» tiene que traer de {minimo} a {maximo} puntos; trae {len(v)}")
        for i, x in enumerate(v, 1):
            if j := sorted({m.group(0) for m in JERGA.finditer(x)}):
                problemas.append(f"«{campo}» {i} trae jerga o cifras internas: {', '.join(j)}. "
                                 "Di los segundos como «segundo 4» y no cites porcentajes")
            if len(x) > caracteres:
                problemas.append(f"«{campo}» {i} mide {len(x)} caracteres; el máximo es {caracteres}")
    for campo in ("por_que", "lo_que_funciona", "que_cambiar"):
        if j := sorted({m.group(0) for m in JERGA.finditer(salida[campo])}):
            problemas.append(f"«{campo}» trae jerga o cifras internas que la persona no debe ver: {', '.join(j)}. "
                             "Di los segundos como «segundo 4» y no cites porcentajes")
        if len(salida[campo]) > MAX_CARACTERES:
            problemas.append(f"«{campo}» mide {len(salida[campo])} caracteres; el máximo es {MAX_CARACTERES}")
    if salida["que_cambiar"].strip() and not 1 <= len(pasos) <= MAX_PASOS:
        problemas.append(f"«pasos» tiene que traer de 1 a {MAX_PASOS} pasos para hacer el cambio en el editor")
    if not salida["que_cambiar"].strip() and pasos:
        problemas.append("sin cambio no van «pasos»")
    for i, p in enumerate(pasos, 1):
        if j := sorted({m.group(0) for m in JERGA.finditer(p)}):
            problemas.append(f"el paso {i} trae jerga o cifras internas: {', '.join(j)}")
        if len(p) > MAX_CARACTERES_PASO:
            problemas.append(f"el paso {i} mide {len(p)} caracteres; el máximo es {MAX_CARACTERES_PASO}")
    if salida["anzuelo_detectado"] != "ninguno":
        if not salida.get("anzuelo_frase", "").strip():
            problemas.append("marcaste un anzuelo pero no dijiste cuál frase o qué se ve en «anzuelo_frase»")
        if not salida["que_cambiar"].strip():
            problemas.append("el video trae un anzuelo: «que_cambiar» tiene que decir cómo quitarlo")
        if not 0 <= salida.get("anzuelo_momento_s", -1) <= datos["duracion_video_s"]:
            problemas.append("«anzuelo_momento_s» tiene que ser el segundo del video donde aparece el anzuelo")
    visibles = [salida["por_que"], salida["lo_que_funciona"], salida["que_cambiar"], salida.get("anzuelo_frase") or "",
                *salida["storyboard"], *pasos, *bueno, *mejoras, *lista(salida, "lo_flojo"), *sin_verificar]
    if ligas := enlaces(" ".join(visibles)):
        problemas.append(f"la tarjeta no puede llevar enlaces, correos ni dominios: {', '.join(ligas)}")
    frase = _sin_signos(salida.get("anzuelo_frase") or "")
    if salida["anzuelo_detectado"] != "ninguno" and frase and frase not in _fuente(datos):
        problemas.append("«anzuelo_frase» tiene que ser copia de lo que se dice o se lee en el video, tal como aparece")
    if n := cifras_inventadas(salida, datos):
        problemas.append(f"cifras que no vienen en los datos: {', '.join(n)}")
    if not 0 <= salida["momento_s"] <= datos["primer_cuarto_s"][1]:
        problemas.append(f"momento_s {salida['momento_s']} fuera del arranque (0 a {datos['primer_cuarto_s'][1]} s)")
    if datos["nivel_de_riesgo"] in ("alto", "medio") and not salida["que_cambiar"].strip() and salida["anzuelo_detectado"] == "ninguno":
        problemas.append("el nivel no es «bajo» y no trae un cambio")
    return problemas


def cuerpo(datos: dict, aviso: str = "", esfuerzo: str = "high") -> dict:
    texto = meta_api.como_dato("DATOS_DEL_ARRANQUE", json.dumps(datos, ensure_ascii=False))
    if aviso:
        texto += f"\n\nTu respuesta anterior fue bloqueada por esto: {aviso}. Corrígelo."
    return {
        "model": MODELO,
        "reasoning": {"effort": esfuerzo},
        "max_output_tokens": 16000,
        "prompt_cache_key": "retina-explicar-v9",  # gitleaks:allow (etiqueta de caché, no es llave)
        "store": False,
        "text": {"format": {"type": "json_schema", "name": "explicacion_v5", "strict": True, "schema": esquema()}},
        "input": [
            {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": instrucciones()}]},
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": texto}]},
        ],
    }


def pedir_abierto(datos: dict, aviso: str) -> dict:
    """La misma tarjeta con Muse Spark Open (pesos abiertos) en Baseten: mismas instrucciones,
    mismos datos y el mismo validador después."""
    from . import baseten
    c = cuerpo(datos, aviso)
    props = esquema()["properties"]
    campos = "; ".join(f"«{k}»: " + ("uno de " + ", ".join(v["enum"]) if "enum" in v else v["type"]) for k, v in props.items())
    formato = ("\n\nFORMATO DE RESPUESTA: devuelve solo un objeto JSON válido, sin texto antes ni después y sin "
               f"bloques de código, con exactamente estas claves: {campos}. Las listas son listas de textos.")
    mensajes = [{"role": "system", "content": c["input"][0]["content"][0]["text"] + formato},
                {"role": "user", "content": c["input"][1]["content"][0]["text"]}]
    # Razonamiento de fábrica: medido el 28-oct en 50 casos, en alto no pasó más tarjetas a la primera
    # (22 contra 28). Como Spark 1.3, a veces gasta la salida pensando y no escribe el JSON: se repite
    # con más espacio.
    for tope in (8000, 14000):
        texto = baseten.chat("explicar", mensajes, esquema(), max_tokens=tope)
        i, f = texto.find("{"), texto.rfind("}")
        if i >= 0 and f > i:
            try:
                return json.loads(texto[i:f + 1])
            except json.JSONDecodeError:
                pass
    raise RuntimeError("Spark Open no devolvió la explicación en JSON.")


def pedir(datos: dict, aviso: str, motor: str = "api") -> dict:
    """Con razonamiento alto, Spark a veces gasta toda la salida pensando y no escribe nada
    (medido el 27-oct: 5,998 de 6,000 tokens). Si llega vacía, se repite pensando menos."""
    if motor == "abierto":
        return pedir_abierto(datos, aviso)
    for esfuerzo in ("high", "medium"):
        texto = meta_api.texto_de(meta_api.responder("explicar", cuerpo(datos, aviso, esfuerzo)))
        if texto.strip():
            return json.loads(texto)
    raise RuntimeError("Spark no devolvió la explicación ni con razonamiento medio.")


# «abierto+api»: Spark Open (pesos abiertos) escribe la tarjeta y Spark 1.3 solo rescata la que el
# validador le rechazó dos veces. En una vuelta, medido el 28-oct en 50 casos, Spark Open escribe de 35 a 39
# (varía entre corridas); como agente, con herramientas, cierra casi todos (eval/casos_agente.py).
MOTORES = {"api": ("api",), "abierto": ("abierto",), "abierto+api": ("abierto", "api")}
MOTOR_POR_OMISION = "abierto+api"  # el agente en Spark Open cerró 50 de 50 casos (28-oct)


def motor_por_omision() -> str:
    """RETINA_MOTOR del .env, leído al usarse (al importar el .env todavía no se ha cargado)."""
    meta_api._cargar_env()
    motor = os.environ.get("RETINA_MOTOR") or MOTOR_POR_OMISION
    if motor not in MOTORES:
        raise ValueError(f"RETINA_MOTOR debe ser uno de {', '.join(MOTORES)}; dice «{motor}».")
    return motor


def escribir(datos: dict, motores: tuple, pedir=pedir) -> tuple[dict, list, str]:
    """Pide la tarjeta a cada motor en orden, dos intentos cada uno, hasta que una pase el validador.
    Devuelve la última tarjeta, los intentos y qué motor la escribió."""
    salida, intentos = None, []
    for k, motor in enumerate(motores):
        aviso, hay_rescate = "", k + 1 < len(motores)
        for intento in range(2):
            try:
                s = pedir(datos, aviso, motor)
                problemas = revisar(s, datos)
            except (RuntimeError, TypeError, KeyError, AttributeError, ValueError) as e:  # ValueError: JSON truncado
                if not hay_rescate and not (isinstance(e, ValueError) and intento == 0):
                    raise
                intentos.append({"motor": motor, "sugerencia": "", "problemas": [f"respuesta con formato inválido ({type(e).__name__})"]})
                continue
            salida = s
            intentos.append({"motor": motor, "sugerencia": s["que_cambiar"], "problemas": problemas})
            if not problemas:
                return salida, intentos, motor
            aviso = "; ".join(problemas)
    return salida, intentos, motores[-1]


def tarjeta_sin_validar() -> dict:
    """Lo único que sale cuando el validador rechazó la tarjeta dos veces: nada de lo que escribió el modelo
    (ni «por_que», ni «lo_bueno», ni el anzuelo citado), porque nada que no pasó el validador llega a la persona."""
    return dict(por_que="", lo_que_funciona="", lo_bueno=[], lo_flojo=[], que_cambiar="", pasos=[],
                mejoras_opcionales=[], tipo_de_cambio="ninguno", momento_s=0.0, anzuelo_detectado="ninguno",
                anzuelo_frase="", anzuelo_momento_s=-1, confianza="baja", storyboard=[],
                no_pude_verificar=["No hubo una sugerencia que pasara el validador y el filtro de integridad."])


def explicar(carpeta: Path, arranque: dict, motor: str = "", nombre: str = "explicar.json", idioma: str = "es") -> dict:
    motor = motor or motor_por_omision()
    datos = datos_del_arranque(carpeta, arranque)
    if idioma == "en":  # la tarjeta sale en el idioma del panel de quien subió el video
        datos["idioma_de_la_tarjeta"] = "inglés"
    salida, intentos, quien = escribir(datos, MOTORES[motor])
    if intentos[-1]["problemas"]:
        salida = tarjeta_sin_validar()
    from . import baseten
    salida["licencia"] = {"modelo": baseten.MODELO if quien == "abierto" else MODELO,
                          "servido_por": "Baseten" if quien == "abierto" else "Meta Model API",
                          "instrucciones": "skills/explicar.md (explicar-v9)",
                          "reglas": integridad.reglas()["version"], "intentos": intentos,
                          "rescate": quien != MOTORES[motor][0]}
    (carpeta / nombre).write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    return salida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("carpeta", type=Path)
    ap.add_argument("--motor", choices=list(MOTORES), default="",
                    help="api: Spark 1.3 · abierto: Muse Spark Open en Baseten · abierto+api: Spark Open con rescate de Spark 1.3.")
    a = ap.parse_args()
    arranque = json.loads((a.carpeta / "resultado.json").read_text(encoding="utf-8"))["arranque"]
    motor = a.motor or motor_por_omision()
    s = explicar(a.carpeta, arranque, motor, "explicar.json" if motor == "api" else f"explicar-{motor.replace('+', '-y-')}.json")
    print(json.dumps({k: s[k] for k in ("por_que", "que_cambiar", "momento_s", "confianza", "anzuelo_detectado")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
