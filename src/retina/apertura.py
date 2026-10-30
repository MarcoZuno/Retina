"""Servicio «apertura»: el arranque del video, reescrito, dibujado y comprobado.

Retina no califica el arranque: lo devuelve arreglado. Muse Spark Open escribe de nuevo los primeros 10 a 15
segundos y reglas fijas de código revisan el texto: sin anzuelos, sin tocar lo intocable, sin cifras ni nombres
que no salgan del video, el tema del título en la primera frase y el largo. Muse Image dibuja el primer cuadro y
SAM 3.1 busca en él lo que promete el título. Si algo falla, Spark Open lo corrige con la lista exacta de lo que
falló, hasta MAX_CORRECCIONES veces. Nada que no pase llega a la persona. El título nunca se toca.

Lo que Retina no sabe: si esta apertura retiene más gente. Eso nunca se midió y aquí no se promete.

Cuesta, así que corre solo cuando la persona lo pide (en la app, el botón; aquí, --aprobar).

Uso:
    python -m retina.apertura CARPETA [--idioma es|en] [--aprobar]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path

from . import baseten, explicar, integridad, meta_api, sam, storyboard, transcribir
from .esquemas import RAIZ

VERSION = "apertura-v1"
MAX_CORRECCIONES = 2
MIN_PALABRAS, MAX_PALABRAS = 18, 45  # de 10 a 15 segundos, hablando a unas 2.5 a 3 palabras por segundo
MAX_CARACTERES_CUADRO = 400
MIN_CLAVES_TITULO = 3  # con menos, es un título de trabajo («VERSION 1»), no una promesa
MAX_PALABRAS_RESTO = 1200
SEGUNDOS_ANTES = 15
IDIOMAS = {"es": "español", "en": "inglés"}
COMPROBACIONES = ("anzuelos", "intocables", "cifras", "nombres", "tema", "largo", "cuadros")
# USD: 3 vueltas de Spark Open, hasta 5 dibujos y 3 revisiones de SAM (medido en eval/apertura_casos.py)
COSTO_MAXIMO_USD = 0.25
VACIAS = frozenset("""para como este esta esto estos estas pero porque cuando donde desde hasta sobre entre tiene tienen
    hace hacer puede pueden todo toda todos todas cada algo alguien nada mucho muchos muchas poco muy mas menos solo
    sus nos les que quien cual cuales eres eran fue fueron ser son esta ahora aqui asi tan tus mis with that this
    from your have what when where which their there about into will would could should them they these those
    just like than then been were does""".split())
# Cifras con letra. Sin «uno», «one» ni «once»: en una frase casi nunca son una cantidad.
LETRA = {"dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "doce": 12,
         "quince": 15, "veinte": 20, "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80,
         "noventa": 90, "cien": 100, "mil": 1000, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
         "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000}
FORMATO = ("\n\nFORMATO DE RESPUESTA: devuelve solo un objeto JSON válido, sin texto antes ni después y sin bloques de "
           "código, con exactamente estas claves: «voz»: texto; «cuadros»: lista de tres textos.")


def instrucciones() -> str:
    return (RAIZ / "skills" / "apertura.md").read_text(encoding="utf-8").split("---", 2)[2].strip()


def _palabras(texto: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", integridad.normalizar(texto))


def _numeros(texto: str) -> set[float]:
    hallados = set()
    for n in re.findall(r"\d+(?:[.,]\d+)*", texto):
        miles = re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", n)
        hallados.add(float(re.sub(r"[.,]", "", n) if miles else n.replace(",", ".")))
    return hallados | {float(LETRA[p]) for p in _palabras(texto) if p in LETRA}


def cifras_nuevas(voz: str, fuente: str) -> list[str]:
    return sorted(f"{n:g}" for n in _numeros(voz) - _numeros(fuente) - {0.0, 1.0})


def nombres_nuevos(voz: str, fuente: str) -> list[str]:
    """Palabras con mayúscula a media frase que el video no dice. La primera de cada frase no se juzga."""
    conocidas = set(_palabras(fuente))
    return sorted({p for frase in re.split(r"(?<=[.!?…:])\s+", voz) for p in re.findall(r"[^\W\d_]+", frase)[1:]
                   if p[0].isupper() and integridad.normalizar(p) not in conocidas})


def tema_llega_tarde(voz: str, titulo: str) -> bool:
    claves = {p for p in _palabras(titulo) if len(p) >= 4 and p not in VACIAS}
    if len(claves) < MIN_CLAVES_TITULO:
        return False
    primera = re.split(r"(?<=[.!?…])\s+", voz.strip(), maxsplit=1)[0]
    return not {p[:4] for p in claves} & {p[:4] for p in _palabras(primera)}  # «panes» cuenta como «pan»


def revisar(s: dict, datos: dict) -> list[dict]:
    """Las reglas de texto, en código, después del modelo. Devuelve lo que falló, con el detalle para corregirlo."""
    voz, cuadros = s.get("voz"), s.get("cuadros")
    if not isinstance(voz, str) or not isinstance(cuadros, list) or not all(isinstance(c, str) for c in cuadros):
        return [{"id": "formato", "detalle": "la respuesta tiene que traer «voz» (texto) y «cuadros» (lista de textos)"}]
    problemas = []

    def fallo(id_: str, detalle: str) -> None:
        problemas.append({"id": id_, "detalle": detalle})

    fuente, titulo = datos["fuente"], datos["titulo"]
    todo = " ".join([voz, *cuadros])
    for r in integridad.revisar(todo):
        fallo("anzuelos", f"{r['regla']} (frases: {', '.join(r['frases'])})")
    if t := explicar.toca_intocable(todo):
        fallo("intocables", f"toca algo intocable: {', '.join(t)}")
    if n := cifras_nuevas(voz, fuente):
        fallo("cifras", f"cifras que no vienen en los datos del video: {', '.join(n)}")
    if n := nombres_nuevos(voz, fuente):
        fallo("nombres", f"nombres que no vienen en los datos del video: {', '.join(n)}")
    if tema_llega_tarde(voz, titulo):
        fallo("tema", "la primera frase tiene que decir de qué trata el video con palabras del título")
    if not MIN_PALABRAS <= (n := len(voz.split())) <= MAX_PALABRAS:
        fallo("largo", f"la voz mide {n} palabras y tiene que medir de {MIN_PALABRAS} a {MAX_PALABRAS}")
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


def lazo(datos: dict, concepto: str | None, pedir, dibujar, medir, avisar=_nada_que_avisar) -> dict:
    """Escribe, revisa y corrige. `dibujar(i, cuadro, objeto)` deja el cuadro i y `medir(imagen, concepto)` lo busca
    con SAM; los dos cuestan, así que solo corren si el texto ya pasó. El primer cuadro se dibuja antes que los
    otros: si SAM no ve la promesa, los otros dos no se pagan."""
    intentos, no_comprobe, aviso, s, primero, vista = [], [], "", None, None, None
    for vuelta in range(MAX_CORRECCIONES + 1):
        avisar("corrigiendo" if vuelta else "escribiendo", vuelta)
        vista = None
        try:
            s = pedir(datos, aviso)
            problemas = revisar(s, datos)
        except meta_api.TopeAlcanzado:
            raise
        except RuntimeError as e:
            s, problemas = None, [{"id": "formato", "detalle": f"no llegó una respuesta válida ({type(e).__name__})"}]
        if not problemas and concepto:
            avisar("dibujando", vuelta)
            primero = dibujar(1, s["cuadros"][0], concepto)
            avisar("buscando", vuelta)
            vista = _sin_dato_falso(medir, primero, concepto)
            if "error" in vista:
                no_comprobe.append("promesa")
                vista = None
            elif not vista.get("aparece") or vista["primer_segundo"] >= 1:
                problemas = [{"id": "promesa", "detalle": f"en el primer cuadro no se ve «{concepto}»: tiene que ser "
                                                          "lo principal de la escena, grande y al centro"}]
        intentos.append({"vuelta": vuelta, "problemas": problemas})
        if not problemas:
            break
        aviso = "; ".join(p["detalle"] for p in problemas)
    fallos = {p["id"]: p for p in intentos[-1]["problemas"]}
    comprobaciones = [] if "formato" in fallos else [{"id": c, "paso": c not in fallos} for c in COMPROBACIONES]
    if vista is not None:
        comprobaciones.append({"id": "promesa", "paso": "promesa" not in fallos, "objeto": concepto,
                               "pct_maximo_del_cuadro": vista.get("pct_maximo_del_cuadro")})
    if fallos:
        return {"aprobada": False, "vueltas": len(intentos) - 1, "despues": None, "comprobaciones": comprobaciones,
                "intentos": intentos, "no_comprobe": no_comprobe}
    avisar("terminando", len(intentos) - 1)
    imagenes = [primero if concepto else dibujar(1, s["cuadros"][0], None),
                dibujar(2, s["cuadros"][1], None), dibujar(3, s["cuadros"][2], None)]
    return {"aprobada": True, "vueltas": len(intentos) - 1,
            "despues": {"voz": s["voz"], "cuadros": s["cuadros"], "imagenes": [p.name for p in imagenes]},
            "comprobaciones": comprobaciones, "intentos": intentos, "no_comprobe": no_comprobe}


def quien_escribe() -> tuple[str, str]:
    """Muse Spark Open si hay llave de Baseten; si no, Muse Spark 1.3: con la pura llave de Meta también funciona."""
    meta_api._cargar_env()
    return (baseten.MODELO, "Baseten") if os.environ.get("BASETEN_API_KEY", "").strip() else (explicar.MODELO, "Meta Model API")


def esquema() -> dict:
    return {"type": "object", "additionalProperties": False, "required": ["voz", "cuadros"], "properties": {
        "voz": {"type": "string"}, "cuadros": {"type": "array", "items": {"type": "string"}}}}


def _pedir_spark(sistema: str, texto: str) -> dict:
    cuerpo = {"model": explicar.MODELO, "reasoning": {"effort": "medium"}, "max_output_tokens": 8000, "store": False,
              "text": {"format": {"type": "json_schema", "name": "apertura_v1", "strict": True, "schema": esquema()}},
              "input": [{"type": "message", "role": "developer", "content": [{"type": "input_text", "text": sistema}]},
                        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": texto}]}]}
    try:
        return json.loads(meta_api.texto_de(meta_api.responder("apertura", cuerpo)))
    except json.JSONDecodeError as e:
        raise RuntimeError("Spark 1.3 no devolvió la apertura en JSON.") from e


def pedir(datos: dict, aviso: str = "") -> dict:
    """Como en la tarjeta, Spark Open a veces gasta la salida pensando: se repite con más espacio."""
    para_el_modelo = {k: v for k, v in datos.items() if k != "fuente"}
    texto = f"<<<DATOS_DEL_VIDEO (dato)\n{json.dumps(para_el_modelo, ensure_ascii=False)}\nDATOS_DEL_VIDEO>>>"
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


def dibujar_cuadro(carpeta: Path, i: int, cuadro: str, objeto: str | None) -> Path:
    prompt = storyboard.ESTILO.format(i=i) + cuadro + (f" Main subject, large and centered: {objeto}." if objeto else "")
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
    return {**datos, "titulo": titulo, "resto_de_lo_que_se_dice": " ".join(resto.split()[:MAX_PALABRAS_RESTO]),
            "idioma_de_la_apertura": IDIOMAS[lengua], "fuente": integridad.normalizar(" ".join([titulo, *dicho, *pantalla]))}


def antes_del_cambio(carpeta: Path, datos: dict) -> dict:
    """Lo que el borrador hace hoy: lo que dice en esos segundos, su primer cuadro y lo que vio SAM, si lo revisó."""
    voz = " ".join(f["dice"] for f in datos.get("frases", []) if f["segundo"] < SEGUNDOS_ANTES)
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
        concepto = json.loads(vista.read_text(encoding="utf-8")).get("concepto")
        if concepto:
            return concepto
    return sam.objeto_del_titulo(titulo) if titulo.strip() else None


def armar(carpeta: Path, titulo: str, concepto: str | None, idioma: str = "es", avisar=_nada_que_avisar) -> dict:
    datos = datos_de_apertura(carpeta, titulo, idioma)
    medido = lazo(datos, concepto, pedir, lambda i, c, o: dibujar_cuadro(carpeta, i, c, o), sam.medir_imagen, avisar)
    if not medido["aprobada"]:  # lo que no pasó no se queda en la carpeta del caso
        for i in (1, 2, 3):
            (carpeta / f"apertura-cuadro{i}-ilustracion-ia.png").unlink(missing_ok=True)
    modelo, servido_por = quien_escribe()
    return {"version": VERSION, "titulo": titulo, "idioma": datos["idioma_de_la_apertura"], "objeto": concepto,
            "antes": antes_del_cambio(carpeta, datos), **medido,
            "licencia": {"escribio": modelo, "servido_por": servido_por, "dibujo": storyboard.MODELO, "reviso": sam.MODELO,
                         "instrucciones": f"skills/apertura.md ({VERSION})", "reglas": integridad.reglas()["version"]}}


def rehacer(carpeta: Path, idioma: str = "es", avisar=_nada_que_avisar) -> dict:
    """La apertura de una revisión ya hecha. Una vez hecha no se vuelve a pagar: se regresa la misma."""
    ruta = carpeta / "apertura.json"
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))
    archivo = carpeta / "resultado.json"
    resultado = json.loads(archivo.read_text(encoding="utf-8"))
    titulo = (resultado.get("video") or {}).get("titulo") or ""
    salida = armar(carpeta, titulo, prometido(carpeta, titulo), idioma, avisar)
    ruta.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    resultado["apertura"] = salida
    archivo.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
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
