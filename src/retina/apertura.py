"""Servicio «apertura»: el arranque del video, reescrito, dibujado y comprobado.

Retina no califica el arranque: lo devuelve arreglado. Muse Spark Open escribe de nuevo los primeros 10 a 15
segundos y reglas fijas de código revisan el texto: sin anzuelos, sin tocar lo intocable, sin cifras ni nombres
que no salgan del video, el tema del título en la primera frase y el largo. Muse Spark 1.3 lee la apertura contra todo lo
que dice el video. Muse Image dibuja el primer cuadro y SAM 3.1 busca en él lo que promete el título. Si algo falla, Spark Open lo corrige con la lista exacta de lo que
falló, hasta MAX_CORRECCIONES veces. Cumple la promesa con su primera prueba, sin resumir el video. Nada que no pase llega a la persona. El título nunca se toca.

Lo que Retina no sabe: si esta apertura retiene más gente. Eso nunca se midió y aquí no se promete.

No reescribe videos de fuera de alcance ni consejos de salud: Muse Spark 1.3 lo decide antes de gastar y se le dice a la persona.

Cuesta, así que corre solo cuando la persona lo pide (en la app, el botón; aquí, --aprobar).

Uso:
    python -m retina.apertura CARPETA [--idioma es|en] [--aprobar]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import unicodedata
from pathlib import Path

from . import baseten, explicar, integridad, meta_api, sam, storyboard, transcribir
from .esquemas import RAIZ

VERSION = "apertura-v4"
MAX_CORRECCIONES = 2
MIN_PALABRAS, MAX_PALABRAS = 25, 45  # de 10 a 15 segundos, hablando a unas 2.5 a 3 palabras por segundo
PALABRAS_POR_SEGUNDO = 2.5
MIN_INICIO_REAL = 18  # menos que esto en 15 segundos es casi no decir nada
MIN_MUDO, MAX_MUDO = 5, 16  # sin voz, el arranque es un texto en pantalla
MAX_CARACTERES_CUADRO = 400
MIN_CLAVES_TITULO = 3  # con menos, es un título de trabajo («VERSION 1»), no una promesa
MAX_PALABRAS_RESTO = 1200
SEGUNDOS_ANTES = 15
IDIOMAS = {"es": "español", "en": "inglés"}
COMPROBACIONES = ("anzuelos", "saludo", "intocables", "cifras", "nombres", "tema", "largo", "una_prueba", "fidelidad", "cuadros")
# USD: 3 vueltas de Spark Open, hasta 5 dibujos y 3 revisiones de SAM (medido en eval/apertura_casos.py)
COSTO_MAXIMO_USD = 0.25
VACIAS = frozenset("""para como este esta esto estos estas pero porque cuando donde desde hasta sobre entre tiene tienen
    hace hacer puede pueden todo toda todos todas cada algo alguien nada mucho muchos muchas poco muy mas menos solo
    sus nos les que quien cual cuales eres eran fue fueron ser son esta ahora aqui asi tan tus mis with that this
    from your have what when where which their there about into will would could should them they these those
    just like than then been were does""".split())
# Cifras con letra. Sin «uno», «one» ni «once»: en una frase casi nunca son una cantidad.
LETRA = {"dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "doce": 12,
         "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
         "veinte": 20, "veintiuno": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
         "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29, "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80,
         "noventa": 90, "cien": 100, "doscientos": 200, "trescientos": 300, "cuatrocientos": 400, "quinientos": 500,
         "seiscientos": 600, "setecientos": 700, "ochocientos": 800, "novecientos": 900, "docena": 12, "docenas": 12,
         "dozen": 12, "dozens": 12, "eleven": 11, "thirteen": 13, "fourteen": 14, "sixteen": 16, "seventeen": 17,
         "eighteen": 18, "nineteen": 19,
         "mil": 1000, "miles": 1000, "millares": 1000, "cientos": 100, "centenares": 100, "decenas": 10,
         "thousands": 1000, "hundreds": 100, "millon": 1e6, "millones": 1e6, "million": 1e6, "millions": 1e6, "billion": 1e9, "billions": 1e9, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
         "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000}
_DECENAS = "treinta cuarenta cincuenta sesenta setenta ochenta noventa twenty thirty forty fifty sixty seventy eighty ninety".split()
_UNIDADES = {"uno": 1, "un": 1, "una": 1, "one": 1, **{k: LETRA[k] for k in "dos tres cuatro cinco seis siete ocho nueve two three four five six seven eight nine".split()}}
COMPUESTO = re.compile(rf"\b({'|'.join(_DECENAS)})(?:\s+y\s+|[\s-]+)({'|'.join(_UNIDADES)})\b")
ENLACE = re.compile(r"https?://|www\.", re.I)
SALUDO = re.compile(r"\b(hola|buenos dias|buenas tardes|buenas noches|bienvenid[oa]s?|que tal|como estan|que onda|hello|welcome|howdy"
                    r"|good (?:morning|afternoon|evening)|(?:hi|hey) (?:everyone|everybody|guys|friends|there|folks|all))\b")
PALABRAS_DEL_TEMA = 12  # un inicio que ya funciona dice de qué trata en sus primeras palabras
ORDINAL = re.compile(r"\b(primero|segundo|tercero|first|second|third)[,:]", re.I)
SERIE_LARGA = re.compile(r"(?:[^,.!?…]{1,40},\s*){2,}[^,.!?…]*\b(?:y|e|o|and|or)\b", re.I)
SERIE_CORTA = re.compile(r"(?:^|[\s:])(?:[^\W\d_]+\s){0,2}[^\W\d_]+,\s(?:[^\W\d_]+\s){0,2}[^\W\d_]+\s(?:y|e|o|and|or)\s(?:[^\W\d_]+\s){0,2}[^\W\d_]+[.!?…]*$", re.I)
# En inglés llevan mayúscula sin ser un nombre. En un cuadro describen la escena; en la voz serían un dato y sí se revisan.
GENTILICIOS = frozenset("""mexican american latin spanish french italian german chinese japanese korean indian brazilian
    argentine colombian peruvian cuban canadian british english irish greek turkish russian arab african asian european""".split())
MIN_LETRAS_ALFABETO = 20
PALABRAS_TEMA_FUERA = 120  # el inicio basta para saber de qué trata el video
FORMATO = ("\n\nFORMATO DE RESPUESTA: devuelve solo un objeto JSON válido, sin texto antes ni después y sin bloques de "
           "código, con exactamente estas claves: «ya_funciona»: true o false; «motivo»: texto; «voz»: texto; «cuadros»: lista de tres textos.")


def instrucciones() -> str:
    return (RAIZ / "skills" / "apertura.md").read_text(encoding="utf-8").split("---", 2)[2].strip()


def _palabras(texto: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", integridad.normalizar(texto))


def _numeros(texto: str, con_letra: bool = True) -> set[float]:
    hallados = set()

    def compuesto(m: re.Match) -> str:
        hallados.add(float(LETRA[m[1]] + _UNIDADES[m[2]]))
        return " "

    limpio = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    texto = COMPUESTO.sub(compuesto, limpio)  # «treinta y cinco» es 35, no 30 y 5
    for n in re.findall(r"\d+(?:[.,]\d+)*", texto):
        if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", n):  # 1,000 y 1.000
            hallados.add(float(re.sub(r"[.,]", "", n)))
        elif n.count(".") + n.count(",") == 1:  # 4.5 y 4,5
            hallados.add(float(n.replace(",", ".")))
        else:  # 30.10.2026 o 1,2,3: cada pieza es una cifra
            hallados.update(float(x) for x in re.split(r"[.,]", n))
    return hallados | ({float(LETRA[p]) for p in re.findall(r"[a-z]+", texto) if p in LETRA} if con_letra else set())


def cifras_nuevas(voz: str, fuente: str, con_letra: bool = True) -> list[str]:
    return sorted(f"{n:g}" for n in _numeros(voz, con_letra) - _numeros(fuente) - {0.0, 1.0})


def nombres_nuevos(voz: str, fuente: str) -> list[str]:
    """Palabras con mayúscula a media frase que el video no dice. La primera de cada frase no se juzga."""
    conocidas = set(_palabras(fuente))
    return sorted({p for frase in re.split(r"(?<=[.!?…])\s+", voz) for p in re.findall(r"[^\W\d_]+", frase)[1:]
                   if p[0].isupper() and integridad.normalizar(p) not in conocidas})


def otro_alfabeto(texto: str) -> bool:
    """Retina escribe en español o en inglés y sus reglas cuentan palabras: en chino o árabe nada aprobaría."""
    letras = [c for c in texto if c.isalpha()]
    latinas = sum(unicodedata.name(c, "").startswith("LATIN") for c in letras)
    return len(letras) >= MIN_LETRAS_ALFABETO and latinas < len(letras) / 2


def _claves(titulo: str) -> set[str]:
    return {p for p in _palabras(titulo) if len(p) >= 4 and p not in VACIAS}


def tema_llega_tarde(voz: str, titulo: str) -> bool:
    claves = _claves(titulo)
    if len(claves) < MIN_CLAVES_TITULO:
        return False
    primera = re.split(r"(?<=[.!?…])\s+", voz.strip(), maxsplit=1)[0]
    return not {p[:4] for p in claves} & {p[:4] for p in _palabras(primera)}  # «panes» cuenta como «pan»


def enumera(voz: str) -> bool:
    """¿Suelta una lista en vez de una sola prueba? Una lista agota lo que el video venía a dar."""
    frases = re.split(r"(?<=[.!?…])\s+", voz.strip())
    return len({m.lower() for m in ORDINAL.findall(voz)}) >= 2 or any(SERIE_LARGA.search(f) or SERIE_CORTA.search(f) for f in frases)


def limites_de_voz(datos: dict) -> tuple[int, int]:
    """Un video de 6 segundos no aguanta una voz de 15. Sin voz en el video, es un texto corto en pantalla."""
    if datos.get("video_mudo"):
        return MIN_MUDO, MAX_MUDO
    duracion = datos.get("duracion_video_s") or 0
    maximo = min(MAX_PALABRAS, max(int(duracion * PALABRAS_POR_SEGUNDO), MIN_MUDO)) if duracion else MAX_PALABRAS
    return min(MIN_PALABRAS, maximo * 2 // 3), maximo


def inicio_real(datos: dict) -> str:
    return " ".join(f["dice"] for f in datos.get("frases", []) if f["segundo"] < SEGUNDOS_ANTES and f["dice"])


def por_que_no_sirve(datos: dict) -> str:
    """Spark puede decir que el inicio ya funciona, pero quien lo confirma es el código. Vacío si de verdad sirve."""
    real = inicio_real(datos)
    if len(real.split()) < MIN_INICIO_REAL:
        return "el inicio casi no dice nada: escribe uno"
    if rotas := integridad.revisar(real):
        return f"el inicio trae un anzuelo ({rotas[0]['regla']}): escribe uno sin él"
    primeras = " ".join(real.split()[:PALABRAS_DEL_TEMA])
    if SALUDO.search(integridad.normalizar(primeras)):
        return "el inicio abre con un saludo: escribe uno"
    if datos.get("tema_obligatorio", True) and tema_llega_tarde(primeras, datos["titulo"]):
        return "el inicio tarda en decir de qué trata: escribe uno"
    if datos.get("promesa_en_el_inicio") is False:
        return "lo que promete el título no se ve en el inicio: escribe uno"
    return ""


def revisar(s: dict, datos: dict) -> list[dict]:
    """Las reglas de texto, en código, después del modelo. Devuelve lo que falló, con el detalle para corregirlo."""
    voz, cuadros = (s.get("voz"), s.get("cuadros")) if isinstance(s, dict) else (None, None)
    if not isinstance(voz, str) or not isinstance(cuadros, list) or not all(isinstance(c, str) for c in cuadros):
        return [{"id": "formato", "detalle": "la respuesta tiene que traer «voz» (texto) y «cuadros» (lista de textos)"}]
    problemas = []

    def fallo(id_: str, detalle: str) -> None:
        problemas.append({"id": id_, "detalle": detalle})

    fuente, titulo = datos["fuente"], datos["titulo"]
    todo = " ".join([voz, *cuadros])
    for r in integridad.revisar(todo):
        fallo("anzuelos", f"{r['regla']} (frases: {', '.join(r['frases'])})")
    if ENLACE.search(todo):
        fallo("anzuelos", "no incluyas enlaces")
    if SALUDO.search(integridad.normalizar(" ".join(voz.split()[:PALABRAS_DEL_TEMA]))):
        fallo("saludo", "no abras con un saludo ni una presentación: entra directo al tema")
    if t := explicar.toca_intocable(todo):
        fallo("intocables", f"toca algo intocable: {', '.join(t)}")
    if n := sorted({*cifras_nuevas(voz, fuente), *(x for c in cuadros for x in cifras_nuevas(c, fuente, con_letra=False))}):
        fallo("cifras", f"cifras que no vienen en los datos del video: {', '.join(n)}")
    en_cuadros = [p for c in cuadros for p in nombres_nuevos(c, fuente) if integridad.normalizar(p) not in GENTILICIOS]
    if n := sorted({*nombres_nuevos(voz, fuente), *en_cuadros}):
        fallo("nombres", f"nombres que no vienen en los datos del video: {', '.join(n)}")
    if datos.get("tema_obligatorio", True) and tema_llega_tarde(voz, titulo):
        fallo("tema", "la primera frase tiene que decir de qué trata el video con palabras del título")
    if enumera(voz):
        fallo("una_prueba", "enumeras varias cosas: da una sola prueba y deja lo demás al video")
    minimo, maximo = limites_de_voz(datos)
    if not minimo <= (n := len(voz.split())) <= maximo:
        fallo("largo", f"la voz mide {n} palabras y tiene que medir de {minimo} a {maximo}")
    if len(cuadros) != 3 or not all(c.strip() for c in cuadros) or any(len(c) > MAX_CARACTERES_CUADRO for c in cuadros):
        fallo("cuadros", f"tienen que ser exactamente 3 cuadros de hasta {MAX_CARACTERES_CUADRO} caracteres")
    return problemas


def _sin_dato_falso(medir, imagen: Path, concepto: str) -> dict:
    """Si SAM no contesta, no hay comprobación: no cuenta como que pasó ni como que falló."""
    try:
        return medir(imagen, concepto)
    except meta_api.TopeAlcanzado:
        raise
    except Exception as e:  # noqa: BLE001 — la apertura sigue; la persona ve qué no se pudo comprobar
        return {"error": type(e).__name__}


def _nada_que_avisar(paso: str, vuelta: int) -> None:
    pass


def _lee_fiel(fiel, voz: str, datos: dict) -> dict | None:
    """Si Spark no contesta, no hay comprobación: no cuenta como que pasó ni como que falló."""
    try:
        return fiel(voz, datos)
    except meta_api.TopeAlcanzado:
        raise
    except Exception:  # noqa: BLE001 — la persona ve qué no se pudo comprobar
        return None


def _revisar_cuadros(imagenes: list[Path], textos: list[str], ya_visto: bool, comprobar) -> list[dict]:
    """SAM busca una cosa en el primer cuadro. Muse Spark 1.3 mira los que SAM no vio. None: no se pudo revisar."""
    filas = []
    for i, (imagen, texto) in enumerate(zip(imagenes, textos), 1):
        if i == 1 and ya_visto:
            continue
        try:
            filas.append({"cuadro": i, "coincide": comprobar(imagen, texto)})
        except meta_api.TopeAlcanzado:
            raise
        except Exception:  # noqa: BLE001 — lo que no se pudo revisar se dice, no cuenta como bueno
            filas.append({"cuadro": i, "coincide": None})
    return filas


def lazo(datos: dict, concepto: str | None, pedir, dibujar, medir, avisar=_nada_que_avisar, comprobar=None, fiel=None) -> dict:
    """Escribe, revisa y corrige. `dibujar(i, cuadro)` deja el cuadro i y `medir(imagen, concepto)` lo busca con SAM;
    los dos cuestan, así que solo corren si el texto ya pasó. `fiel(voz, datos)` lee la apertura contra lo que dice el video. El primer cuadro se dibuja antes que los otros: si SAM no
    ve la promesa, los otros dos no se pagan. Quien escribe sabe qué objeto se va a buscar y debe describirlo: SAM comprueba
    que el dibujo lo muestre, no que la idea sea buena. `comprobar(imagen, texto)` mira los cuadros que SAM no revisó."""
    if concepto:
        datos = {**datos, "objeto_prometido": concepto}
    intentos, no_comprobe, aviso, s, imagenes, vista, revisados = [], [], "", None, [], None, []
    for vuelta in range(MAX_CORRECCIONES + 1):
        avisar("corrigiendo" if vuelta else "escribiendo", vuelta)
        vista, no_comprobe, revisados = None, [], []
        try:
            s = pedir(datos, aviso)
            if isinstance(s, dict) and s.get("ya_funciona"):
                motivo = str(s.get("motivo") or "").strip()
                if not (no_sirve := por_que_no_sirve(datos)) and motivo and not integridad.revisar(motivo) and not ENLACE.search(motivo):
                    intentos.append({"vuelta": vuelta, "problemas": []})
                    return {"aprobada": True, "ya_funciona": True, "motivo": motivo, "vueltas": vuelta, "despues": None,
                            "comprobaciones": [], "intentos": intentos, "no_comprobe": []}
                problemas = [{"id": "ya_funciona", "detalle": no_sirve or "explica en una frase por qué el inicio ya funciona, sin enlaces ni pedidos al público"}]
            else:
                problemas = revisar(s, datos)
        except meta_api.TopeAlcanzado:
            raise
        except RuntimeError as e:
            s, problemas = None, [{"id": "formato", "detalle": f"no llegó una respuesta válida ({type(e).__name__})"}]
        if not problemas:
            try:
                if fiel:  # antes de dibujar: leer cuesta mucho menos que dibujar
                    avisar("leyendo", vuelta)
                    veredicto = _lee_fiel(fiel, s["voz"], datos)
                    if veredicto is None:
                        no_comprobe.append("fidelidad")
                    elif not veredicto["fiel"]:
                        problemas = [{"id": "fidelidad", "detalle": f"lo que dice el video no sostiene esto: {veredicto['que_agrega'][:300]}. "
                                                                    "Usa solo lo que el video dice, sin agregar ni exagerar"}]
                if not problemas:
                    avisar("dibujando", vuelta)
                    primero = dibujar(1, s["cuadros"][0])
                    if concepto:
                        avisar("buscando", vuelta)
                        vista = _sin_dato_falso(medir, primero, concepto)
                        if "error" in vista:
                            no_comprobe.append("promesa")
                            vista = None
                        elif not vista.get("aparece") or vista["primer_segundo"] >= 1:
                            problemas = [{"id": "promesa", "detalle": f"en el primer cuadro no se ve «{concepto}»: tiene que "
                                                                      "ser lo principal de la escena, grande y al centro"}]
                if not problemas:
                    avisar("terminando", vuelta)
                    imagenes = [primero, dibujar(2, s["cuadros"][1]), dibujar(3, s["cuadros"][2])]
                    if comprobar:
                        avisar("mirando", vuelta)
                        revisados = _revisar_cuadros(imagenes, s["cuadros"], vista is not None, comprobar)
                        if malos := [r["cuadro"] for r in revisados if r["coincide"] is False]:
                            problemas = [{"id": "cuadros", "detalle": f"el dibujo del cuadro {', '.join(map(str, malos))} no muestra lo que "
                                                                      "describe: pide una escena más simple y concreta"}]
            except meta_api.TopeAlcanzado:
                raise
            except Exception as e:  # noqa: BLE001 — Muse Image puede rechazar una escena: se pide otra
                problemas = [{"id": "cuadros", "detalle": f"no se pudo dibujar un cuadro ({type(e).__name__}): describe otra escena"}]
        intentos.append({"vuelta": vuelta, "problemas": problemas})
        if not problemas:
            break
        aviso = "; ".join(p["detalle"] for p in problemas)
    fallos = {p["id"]: p for p in intentos[-1]["problemas"]}
    sin_correr = {"fidelidad"} if not fiel or "fidelidad" in no_comprobe else set()
    if not datos.get("tema_obligatorio", True) or len(_claves(datos["titulo"])) < MIN_CLAVES_TITULO:
        sin_correr.add("tema")
    comprobaciones = [] if "formato" in fallos else [{"id": c, "paso": c not in fallos} for c in COMPROBACIONES if c not in sin_correr]
    if vista is not None:
        comprobaciones.append({"id": "promesa", "paso": "promesa" not in fallos, "objeto": vista.get("concepto", concepto),
                               "pct_maximo_del_cuadro": vista.get("pct_maximo_del_cuadro")})
    if fallos:
        return {"aprobada": False, "vueltas": len(intentos) - 1, "despues": None, "comprobaciones": comprobaciones,
                "intentos": intentos, "no_comprobe": no_comprobe}
    return {"aprobada": True, "vueltas": len(intentos) - 1,
            "despues": {"voz": s["voz"], "cuadros": s["cuadros"], "imagenes": [p.name for p in imagenes],
                        "cuadros_revisados": revisados},
            "comprobaciones": comprobaciones, "intentos": intentos, "no_comprobe": no_comprobe}


def quien_escribe() -> tuple[str, str]:
    """Muse Spark Open si hay llave de Baseten; si no, Muse Spark 1.3: con la pura llave de Meta también funciona."""
    meta_api._cargar_env()
    return (baseten.MODELO, "Baseten") if os.environ.get("BASETEN_API_KEY", "").strip() else (explicar.MODELO, "Meta Model API")


def esquema() -> dict:
    return {"type": "object", "additionalProperties": False, "required": ["ya_funciona", "motivo", "voz", "cuadros"], "properties": {
        "ya_funciona": {"type": "boolean"}, "motivo": {"type": "string"},
        "voz": {"type": "string"}, "cuadros": {"type": "array", "items": {"type": "string"}}}}


ESQUEMA_CUADRO = {"type": "object", "additionalProperties": False, "required": ["coincide", "que_se_ve"],
                  "properties": {"coincide": {"type": "boolean"}, "que_se_ve": {"type": "string"}}}


def comprobar_cuadro(imagen: Path, cuadro: str) -> bool:
    """Muse Spark 1.3 mira el dibujo y contesta si muestra lo principal de lo que se escribió."""
    sistema = (RAIZ / "skills" / "cuadro.md").read_text(encoding="utf-8").split("---", 2)[2].strip()
    url = "data:image/png;base64," + base64.b64encode(imagen.read_bytes()).decode()
    cuerpo = {"model": explicar.MODELO, "reasoning": {"effort": "low"}, "max_output_tokens": 2000, "store": False,
              "text": {"format": {"type": "json_schema", "name": "cuadro_v1", "strict": True, "schema": ESQUEMA_CUADRO}},
              "input": [{"type": "message", "role": "developer", "content": [{"type": "input_text", "text": sistema}]},
                        {"type": "message", "role": "user", "content": [
                            {"type": "input_text", "text": meta_api.como_dato("ESCENA_PEDIDA", cuadro)},
                            {"type": "input_image", "image_url": url}]}]}
    return bool(json.loads(meta_api.texto_de(meta_api.responder("cuadro", cuerpo)))["coincide"])


ESQUEMA_FIEL = {"type": "object", "additionalProperties": False, "required": ["fiel", "que_agrega"],
                "properties": {"fiel": {"type": "boolean"}, "que_agrega": {"type": "string"}}}
ESQUEMA_TEMA = {"type": "object", "additionalProperties": False, "required": ["tema", "por_que"],
                "properties": {"tema": {"type": "string", "enum": ["fuera", "salud", "ninguno"]}, "por_que": {"type": "string"}}}


def _preguntar(estacion: str, esquema: dict, nombre: str, texto: str) -> dict:
    sistema = (RAIZ / "skills" / f"{estacion}.md").read_text(encoding="utf-8").split("---", 2)[2].strip()
    cuerpo = {"model": explicar.MODELO, "reasoning": {"effort": "low"}, "max_output_tokens": 2000, "store": False,
              "text": {"format": {"type": "json_schema", "name": nombre, "strict": True, "schema": esquema}},
              "input": [{"type": "message", "role": "developer", "content": [{"type": "input_text", "text": sistema}]},
                        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": texto}]}]}
    return json.loads(meta_api.texto_de(meta_api.responder(estacion, cuerpo)))


def es_fiel(voz: str, datos: dict) -> dict:
    """Muse Spark 1.3 lee la apertura contra todo lo que dice el video. Las reglas revisan cifras y nombres; esto, lo demás."""
    todo = " ".join(datos["fuente"].split()[:2 * MAX_PALABRAS_RESTO])
    texto = meta_api.como_dato("LO_QUE_DICE_EL_VIDEO", todo) + "\n\n" + meta_api.como_dato("APERTURA_NUEVA", voz)
    r = _preguntar("fidelidad", ESQUEMA_FIEL, "fidelidad_v1", texto)
    return {"fiel": bool(r["fiel"]), "que_agrega": str(r["que_agrega"])}


def tema_fuera(titulo: str, dicho: str) -> str | None:
    """«fuera» o «salud» si Retina no debe reescribir este video; None si puede. Corre antes de gastar en escribir."""
    texto = meta_api.como_dato("TITULO", titulo) + "\n\n" + meta_api.como_dato("LO_QUE_SE_DICE", " ".join(dicho.split()[:PALABRAS_TEMA_FUERA]))
    tema = _preguntar("tema", ESQUEMA_TEMA, "tema_v1", texto)["tema"]
    return None if tema == "ninguno" else tema


def _pedir_spark(sistema: str, texto: str) -> dict:
    cuerpo = {"model": explicar.MODELO, "reasoning": {"effort": "medium"}, "max_output_tokens": 8000, "store": False,
              "text": {"format": {"type": "json_schema", "name": "apertura_v2", "strict": True, "schema": esquema()}},
              "input": [{"type": "message", "role": "developer", "content": [{"type": "input_text", "text": sistema}]},
                        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": texto}]}]}
    try:
        return json.loads(meta_api.texto_de(meta_api.responder("apertura", cuerpo)))
    except json.JSONDecodeError as e:
        raise RuntimeError("Spark 1.3 no devolvió la apertura en JSON.") from e


def pedir(datos: dict, aviso: str = "") -> dict:
    """Como en la tarjeta, Spark Open a veces gasta la salida pensando: se repite con más espacio."""
    para_el_modelo = {k: v for k, v in datos.items() if k != "fuente"}
    texto = meta_api.como_dato("DATOS_DEL_VIDEO", json.dumps(para_el_modelo, ensure_ascii=False))
    if aviso:
        texto += f"\n\nTu intento anterior fue rechazado por esto: {aviso}. Corrígelo."
    if quien_escribe()[1] != "Baseten":
        return _pedir_spark(instrucciones(), texto)
    mensajes = [{"role": "system", "content": instrucciones() + FORMATO}, {"role": "user", "content": texto}]
    for tope in (8000, 14000):
        respuesta = baseten.chat("apertura", mensajes, max_tokens=tope)
        i, f = respuesta.find("{"), respuesta.rfind("}")
        if i >= 0 and f > i:
            try:
                return json.loads(respuesta[i:f + 1])
            except json.JSONDecodeError:
                pass
    raise RuntimeError("Spark Open no devolvió la apertura en JSON.")


def dibujar_cuadro(carpeta: Path, i: int, cuadro: str) -> Path:
    prompt = storyboard.ESTILO.format(i=i) + cuadro
    destino = carpeta / f"apertura-cuadro{i}-ilustracion-ia.png"
    meta_api._revisar_tope(meta_api.PRECIO_IMAGEN[storyboard.MODELO])
    storyboard.dibujar_uno(prompt, destino, servicio="apertura")
    return destino


def datos_de_apertura(carpeta: Path, titulo: str, idioma: str = "es") -> dict:
    """Lo mismo que ve la tarjeta, más lo que se dice después: el dato prometido suele llegar tarde. «fuente» es
    todo lo que el video dice o muestra escrito; contra eso se revisan cifras y nombres, y no va al modelo."""
    datos = explicar.datos_del_arranque(carpeta, {"nivel": "sin_nivel"})
    datos.pop("nivel_de_riesgo")
    voz = carpeta / "transcribir.json"
    turnos = json.loads(voz.read_text(encoding="utf-8")).get("turnos", []) if voz.exists() else []
    dicho = [t["transcript"] for t in turnos if t.get("transcript")]
    fin_ms = datos["primer_cuarto_s"][1] * 1000
    resto = " ".join(t["transcript"] for t in turnos if t.get("transcript") and t["startMs"] >= fin_ms)
    tramos = json.loads((carpeta / "describir.json").read_text(encoding="utf-8"))["tramos"]
    pantalla = [str(t.get("texto_en_pantalla") or "") for t in tramos]
    lengua = transcribir.idioma_de(" ".join([titulo, *" ".join(dicho).split()[:60]])) or idioma
    vista = carpeta / "sam.json"
    promesa = json.loads(vista.read_text(encoding="utf-8")) if vista.exists() else {}
    en_el_inicio = (promesa["aparece"] and promesa.get("primer_segundo", 99) < 3) if "aparece" in promesa else None
    return {**datos, "titulo": titulo, "resto_de_lo_que_se_dice": " ".join(resto.split()[:MAX_PALABRAS_RESTO]),
            "idioma_de_la_apertura": IDIOMAS[lengua], "fuente": " ".join([titulo, *dicho, *pantalla]),
            "video_mudo": not dicho, "promesa_en_el_inicio": en_el_inicio,
            # Con un título en otro idioma que el video, la apertura no puede usar sus palabras.
            "tema_obligatorio": transcribir.idioma_de(titulo) in (None, lengua)}


def antes_del_cambio(carpeta: Path, datos: dict) -> dict:
    """Lo que el borrador hace hoy: lo que dice en esos segundos, su primer cuadro y lo que vio SAM, si lo revisó."""
    voz = " ".join(f["dice"] for f in datos.get("frases", []) if f["segundo"] < SEGUNDOS_ANTES and f["dice"])
    if len(palabras := voz.split()) > MAX_PALABRAS:  # una frase larga se pasa de esos segundos
        voz = " ".join(palabras[:MAX_PALABRAS]) + "…"
    primero = next(iter(sorted((carpeta / "cuadros").glob("c*.jpg"))), None)
    if primero:
        shutil.copyfile(primero, carpeta / "apertura-antes.jpg")
    vista = carpeta / "sam.json"
    promesa = json.loads(vista.read_text(encoding="utf-8")) if vista.exists() else None
    return {"voz": voz, "imagen": "apertura-antes.jpg" if primero else None,
            "promesa": {k: promesa[k] for k in ("concepto", "aparece", "primer_segundo")} if promesa and "aparece" in promesa else None}


def prometido(carpeta: Path, titulo: str) -> str | None:
    """Lo que el título promete que se verá, de la lista cerrada de SAM. Reusa lo que ya se revisó en el borrador."""
    vista = carpeta / "sam.json"
    if vista.exists():
        previo = json.loads(vista.read_text(encoding="utf-8"))
        if objeto := previo.get("objeto") or previo.get("concepto"):
            return objeto
    return sam.objeto_del_titulo(titulo) if titulo.strip() else None


def armar(carpeta: Path, titulo: str, concepto: str | None, idioma: str = "es", avisar=_nada_que_avisar) -> dict:
    datos = datos_de_apertura(carpeta, titulo, idioma)
    medido, sin_tema = None, []
    try:
        dicho = " ".join([*(f["dice"] or "" for f in datos.get("frases", [])), datos["resto_de_lo_que_se_dice"]])
        no_va = {"aprobada": False, "vueltas": 0, "despues": None, "comprobaciones": [], "intentos": [], "no_comprobe": []}
        if otro_alfabeto(f"{titulo} {dicho}"):  # se dice antes de gastar
            medido = {**no_va, "otro_alfabeto": True}
        else:
            try:
                tema = tema_fuera(titulo, dicho)
            except meta_api.TopeAlcanzado:
                raise
            except Exception:  # noqa: BLE001 — sin esta revisión se sigue, y la persona ve que no se hizo
                tema, sin_tema = None, ["tema_sensible"]
            if tema:
                medido = {**no_va, "fuera_de_alcance": tema}
            else:
                medido = lazo(datos, concepto, pedir, lambda i, c: dibujar_cuadro(carpeta, i, c),
                              lambda imagen, c: sam.medir_imagen(imagen, sam.termino(c) or c), avisar, comprobar_cuadro, es_fiel)
                medido["no_comprobe"] = [*sin_tema, *medido["no_comprobe"]]
    finally:
        if not (medido and medido["aprobada"]):  # lo que no pasó no se queda en la carpeta del caso
            for i in (1, 2, 3):
                (carpeta / f"apertura-cuadro{i}-ilustracion-ia.png").unlink(missing_ok=True)
    modelo, servido_por = quien_escribe()
    return {"version": VERSION, "titulo": titulo, "idioma": datos["idioma_de_la_apertura"], "objeto": concepto,
            "modo": "texto_en_pantalla" if datos.get("video_mudo") else "voz",
            "antes": antes_del_cambio(carpeta, datos), **medido,
            "licencia": {"escribio": modelo, "servido_por": servido_por, "dibujo": storyboard.MODELO, "reviso": sam.MODELO,
                         "instrucciones": f"skills/apertura.md ({VERSION})", "reglas": integridad.reglas()["version"]}}


def _escribir(ruta: Path, datos: dict) -> None:
    """Se escribe a un temporal y se reemplaza de un golpe: nadie lee un archivo a medias."""
    temporal = ruta.with_suffix(".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temporal, ruta)


def rehacer(carpeta: Path, idioma: str = "es", avisar=_nada_que_avisar) -> dict:
    """La apertura de una revisión ya hecha. Una aprobada no se vuelve a pagar: se regresa la misma. La que no pasó
    se guarda para enseñar qué falló, pero se puede volver a intentar."""
    ruta, archivo = carpeta / "apertura.json", carpeta / "resultado.json"
    resultado = json.loads(archivo.read_text(encoding="utf-8"))
    salida = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    if not (salida and salida.get("aprobada")):
        titulo = (resultado.get("video") or {}).get("titulo") or ""
        salida = armar(carpeta, titulo, prometido(carpeta, titulo), idioma, avisar)
    resultado["apertura"] = salida
    _escribir(archivo, resultado)
    _escribir(ruta, salida)  # al último: si existe, el resultado ya la trae
    return salida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("carpeta", type=Path)
    ap.add_argument("--idioma", default="es", choices=list(IDIOMAS))
    ap.add_argument("--aprobar", action="store_true", help="Aprobación humana del gasto.")
    a = ap.parse_args()
    print(f"Hasta USD {COSTO_MAXIMO_USD:.2f}.")
    if not a.aprobar:
        print("Sin --aprobar no se genera nada.")
        return
    s = rehacer(a.carpeta, a.idioma, lambda paso, vuelta: print(f"  {paso} (corrección {vuelta})", flush=True))
    print(json.dumps({k: s[k] for k in ("aprobada", "vueltas", "despues", "comprobaciones")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
