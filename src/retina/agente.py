"""Retina como agente: Spark investiga el arranque con herramientas y entrega la tarjeta.

El patrón de las recetas de Meta: el código calcula, el modelo interpreta y un
validador revisa. Las herramientas solo leen lo que ya calcularon las
estaciones (describir, transcribir, el riesgo del arranque y la historia de
videos parecidos). La tarjeta se entrega con `entregar_tarjeta`, y el mismo
validador de «explicar» la revisa dentro del ciclo: si falla, Spark recibe los
problemas y corrige. Guardas: tope de turnos, de llamadas por turno y por revisión,
llamadas repetidas y el tope de gasto del proyecto. Si el ciclo no cierra, cae a «explicar» de una sola vuelta.

El mismo ciclo corre con Spark 1.3 (API de Meta) o con Muse Spark Open (pesos
abiertos, Baseten). Con «abierto+api», Spark Open investiga y escribe, y Spark
1.3 solo rescata el caso si el ciclo de Spark Open no cierra.

Uso:
    python -m retina.agente CARPETA --modelo MODELO.pkl --voz VOZ.jsonl [--motor abierto+api]
        (CARPETA ya trae resultado.json, describir.json y transcribir.json)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import timedelta
from pathlib import Path

from . import baseten, explicar, meta_api
from .curvas import cubeta, regla_de_hoy
from .esquemas import RAIZ
from .predecir import Modelo, caidas
from .voz import BLOQUES, bloques

MODELO = "muse-spark-1.3"
MAX_TURNOS = 12
REPETIDAS = 2  # la misma llamada con los mismos datos, más de esto, corta el ciclo
# Límites de herramientas (cada llamada a SAM cuesta; un modelo desbocado hizo 240 en 12 turnos):
MAX_LLAMADAS_POR_TURNO = 6  # las que se ejecutan en un solo turno; las demás reciben un aviso
MAX_LLAMADAS_TOTAL = 30  # de consulta (todas menos entregar_tarjeta) por revisión y por motor; después solo se puede entregar
MAX_LLAMADAS_SAM = 2  # medir_lo_prometido, por revisión y por motor


def _herramienta(nombre: str, descripcion: str, props: dict) -> dict:
    return {"type": "function", "name": nombre, "description": descripcion,
            "parameters": {"type": "object", "additionalProperties": False, "properties": props, "required": list(props)}}


RANGO = {"desde_s": {"type": "number"}, "hasta_s": {"type": "number"}}
HERRAMIENTAS = [
    _herramienta("ver_arranque", "Título del video, nivel de riesgo del arranque, dónde terminan el gancho y el primer cuarto, "
                 "y cuánta gente se va en videos parecidos en cada parte.", {}),
    _herramienta("ver_tramos", "Lo que se ve en pantalla entre dos segundos: qué pasa, texto en pantalla, "
                 "plano, cambios de plano, presentador.", RANGO),
    _herramienta("oir", "Lo que se dice entre dos segundos (frases con su segundo) y los silencios de 3 s o más.", RANGO),
    _herramienta("buscar_parecidos", "Cómo arrancan videos parecidos ya publicados (misma duración y, si hay, mismo "
                 "talento): su título y lo que dicen en el arranque. «buenos» = retuvieron mejor que sus parecidos; "
                 "«malos» = perdieron más.",
                 {"cuales": {"type": "string", "enum": ["buenos", "malos"]}, "n": {"type": "integer"}}),
    _herramienta("medir_lo_prometido", "SAM 3.1 sobre los primeros 3 s: si aparece lo que promete el título, desde qué "
                 "segundo, en cuántos cuadros y cuánto del cuadro ocupa. El concepto es una frase corta en inglés de un "
                 "objeto o un lugar («flooded road», «sweet bread»). Nunca personas: el código lo rechaza. Cuesta: úsala "
                 "una vez, como mucho dos.", {"concepto": {"type": "string"}}),
    _herramienta("entregar_tarjeta", "Entrega la tarjeta final. El código la revisa; si devuelve problemas, corrige y "
                 "vuelve a entregar.", explicar.esquema()["properties"]),
]
NOMBRES = {h["name"] for h in HERRAMIENTAS}


def titulo_limpio(archivo: str, codigo: str) -> str:
    t = re.sub(r"\d{4}-\d{2}-\d{2}", " ", archivo.replace(codigo, " ") if codigo else archivo)  # sin código no hay qué quitar
    return re.sub(r"\s+", " ", re.sub(r"\.mp4$", "", t, flags=re.I)).strip()


class Caja:
    """Lo que las herramientas pueden leer de un caso. Nada se escribe."""

    def __init__(self, carpeta: Path, modelo: Modelo, voz: dict):
        self.carpeta, self.modelo, self.voz = carpeta, modelo, voz
        self.resultado = json.loads((carpeta / "resultado.json").read_text(encoding="utf-8"))
        self.datos = explicar.datos_del_arranque(carpeta, self.resultado["arranque"])
        self.vistos: list = []

    def ver_arranque(self) -> dict:
        d, v = self.datos, self.resultado["video"]
        campos = ("duracion_video_s", "gancho_s", "primer_cuarto_s", "nivel_de_riesgo",
                  "caida_de_videos_parecidos_pp")
        return {"titulo": titulo_limpio(v.get("titulo") or "", v["codigo"]), **{k: d[k] for k in campos}}

    def ver_tramos(self, desde_s: float, hasta_s: float) -> dict:
        return {"tramos": [t for t in self.datos["tramos"] if t["fin_s"] > desde_s and t["inicio_s"] < hasta_s]}

    def oir(self, desde_s: float, hasta_s: float) -> dict:
        if "frases" not in self.datos:
            return {"aviso": "Este caso no tiene transcripción."}
        return {"voz_arranca_s": self.datos["voz_arranca_s"],
                "frases": [f for f in self.datos["frases"] if desde_s <= f["segundo"] < hasta_s],
                "silencios_s": [s for s in self.datos["silencios_s"] if s[1] > desde_s and s[0] < hasta_s]}

    def buscar_parecidos(self, cuales: str, n: int) -> dict:
        v = self.resultado["video"]
        hasta = max(h["fecha"] for h in self.modelo.filas)
        hist = [h for h in self.modelo.filas if h["cubeta"] == cubeta(v["duracion_s"])
                and h["fecha"] > hasta - timedelta(days=365) and h["codigo"] in self.voz and h["codigo"] != v["codigo"]]
        talento = (v.get("talento") or "").upper()
        mismos = [h for h in hist if talento and h["talento"].upper() == talento]
        grupo = mismos if len(mismos) >= 10 else hist
        filas = []
        for h in grupo[-400:]:
            base, _ = regla_de_hoy(h, self.modelo.filas, self.modelo.filas)
            e = bloques(caidas(h["curva"])) - bloques(caidas(base))
            filas.append((float(e[0] + e[1]), h))
        filas.sort(key=lambda x: x[0], reverse=cuales == "malos")
        salida = []
        for _, h in filas[: max(1, min(int(n), 5))]:
            fin = h["dur"] * BLOQUES[1][1] / 40
            dice = " ".join(str(x) for t, x in self.voz[h["codigo"]] if float(t) < fin)
            salida.append({"titulo": h.get("titulo") or titulo_limpio(h["archivo"], h["codigo"]), "duracion_s": round(h["dur"]),
                           "arranque": "retuvo mejor que sus parecidos" if cuales == "buenos" else "perdió más que sus parecidos",
                           "dice_en_el_arranque": dice[:400]})
        return {"videos": salida, "comparados_con": "mismo talento y duración" if grupo is mismos else "misma duración"}

    def medir_lo_prometido(self, concepto: str) -> dict:
        from .sam import medir
        return medir(self.carpeta, concepto)

    def titulos_ajenos(self, texto: str) -> list[str]:
        """Títulos de otros videos (de buscar_parecidos) que la tarjeta no debe repetir."""
        vistos = [x["titulo"] for s in self.vistos if isinstance(s, dict) for x in s.get("videos", [])]
        return [t for t in vistos if len(t) >= 15 and t.lower()[:40] in texto.lower()]

    def correr(self, nombre: str, args: dict) -> dict:
        if nombre not in NOMBRES:  # nunca se llama un método por el nombre que mande el modelo
            return {"error": f"No existe la herramienta «{nombre}»."}
        if nombre == "entregar_tarjeta":
            faltan = [k for k in explicar.esquema()["required"] if k not in args]
            if faltan:
                return {"aceptada": False, "problemas": [f"faltan campos: {', '.join(faltan)}"]}
            problemas = explicar.revisar(args, {**self.datos, "vistos": self.vistos})
            texto = [args["por_que"], args["que_cambiar"], args["lo_que_funciona"],
                     *(t for campo in explicar.LISTAS for t in explicar.lista(args, campo))]
            if t := self.titulos_ajenos(" ".join(texto)):
                problemas.append(f"la tarjeta repite el título de otro video ({t[0][:40]}…): descríbelo sin citarlo")
            return {"aceptada": not problemas, "problemas": problemas}
        salida = getattr(self, nombre)(**args)
        self.vistos.append(salida)
        return salida


def instrucciones() -> str:
    return (RAIZ / "skills" / "agente.md").read_text(encoding="utf-8").split("---", 2)[2].strip()


ENTREGA = "Entrega la tarjeta con entregar_tarjeta."
HERRAMIENTAS_CHAT = [{"type": "function", "function": {k: h[k] for k in ("name", "description", "parameters")}}
                     for h in HERRAMIENTAS]  # las mismas, en el formato de Chat Completions


class ConSpark13:
    """Spark 1.3 por la API de Meta (Responses API), razonamiento medio."""
    modelo, servido_por = MODELO, "Meta Model API"

    def __init__(self, inicio: str):
        self.conv = [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": inicio}]}]

    def turno(self) -> tuple[list[dict], str]:
        r = meta_api.responder("agente", {
            "model": MODELO, "instructions": instrucciones(), "input": self.conv, "tools": HERRAMIENTAS,
            "parallel_tool_calls": False, "store": False, "reasoning": {"effort": "medium"},
            "max_output_tokens": 16000, "prompt_cache_key": "retina-agente-v3"})  # gitleaks:allow
        salida = r.get("output", [])
        self.conv += [x for x in salida if x.get("type") != "reasoning"]  # sin store no se reenvía el razonamiento
        return ([{"id": x["call_id"], "nombre": x["name"], "argumentos": x.get("arguments") or "{}"}
                 for x in salida if x.get("type") == "function_call"], meta_api.texto_de(r))

    def devolver(self, id_: str, salida: dict) -> None:
        self.conv.append({"type": "function_call_output", "call_id": id_, "output": json.dumps(salida, ensure_ascii=False)})

    def insistir(self) -> None:
        self.conv.append({"type": "message", "role": "user", "content": [{"type": "input_text", "text": ENTREGA}]})


class ConSparkOpen:
    """Muse Spark Open (pesos abiertos) en Baseten, por Chat Completions: mismas instrucciones, mismas
    herramientas y mismo validador. Piensa en alto: escribe peor que Spark 1.3 y pensar más le cuesta poco."""
    modelo, servido_por = baseten.MODELO, "Baseten"

    def __init__(self, inicio: str):
        self.mensajes = [{"role": "system", "content": instrucciones()}, {"role": "user", "content": inicio}]

    def turno(self) -> tuple[list[dict], str]:
        m = baseten.completar("agente", self.mensajes, 16000, "high", HERRAMIENTAS_CHAT)
        llamadas = [{"id": c.id, "nombre": c.function.name, "argumentos": c.function.arguments or "{}"}
                    for c in (m.tool_calls or [])]
        pedidas = [{"id": l["id"], "type": "function", "function": {"name": l["nombre"], "arguments": l["argumentos"]}}
                   for l in llamadas]
        self.mensajes.append({"role": "assistant", "content": m.content or "", **({"tool_calls": pedidas} if pedidas else {})})
        return llamadas, m.content or ""

    def devolver(self, id_: str, salida: dict) -> None:
        self.mensajes.append({"role": "tool", "tool_call_id": id_, "content": json.dumps(salida, ensure_ascii=False)})

    def insistir(self) -> None:
        self.mensajes.append({"role": "user", "content": ENTREGA})


CONVERSADORES = {"api": ConSpark13, "abierto": ConSparkOpen}
# «abierto+api»: el agente corre en Spark Open (pesos abiertos) y Spark 1.3 solo rescata el caso si su ciclo no cierra.
MOTORES = explicar.MOTORES


def ciclo(caja, conv) -> tuple[dict | None, list, str | None]:
    """Un modelo investiga con las herramientas hasta que el validador acepta su tarjeta o se acaban los turnos."""
    traza, cuenta, consultas, sam = [], {}, 0, 0
    for turno in range(1, MAX_TURNOS + 1):
        try:
            llamadas, texto = conv.turno()
        except meta_api.TopeAlcanzado:
            raise  # el tope no se rodea con el respaldo: también gasta
        except Exception as e:  # noqa: BLE001 — falla de red o de la API: pasa al rescate o al respaldo
            return None, traza, f"{type(e).__name__} en el turno {turno}"
        if not llamadas:
            traza.append({"turno": turno, "texto": texto[:300]})
            conv.insistir()
            continue
        tarjeta, en_turno, tope_llegado = None, 0, False
        for c in llamadas:
            try:
                args = json.loads(c["argumentos"] or "{}")
            except json.JSONDecodeError:
                args = {"_invalidos": True}
            huella = hashlib.sha1(f"{c['nombre']}{json.dumps(args, sort_keys=True)}".encode()).hexdigest()
            cuenta[huella] = cuenta.get(huella, 0) + 1
            en_turno += 1
            consulta = c["nombre"] != "entregar_tarjeta"
            if cuenta[huella] > REPETIDAS:
                res = {"error": "Ya hiciste esta misma llamada. Usa lo que ya tienes y entrega la tarjeta."}
            elif en_turno > MAX_LLAMADAS_POR_TURNO:
                res = {"error": f"Máximo {MAX_LLAMADAS_POR_TURNO} llamadas por turno. Usa lo que ya tienes y entrega la tarjeta."}
            elif consulta and consultas >= MAX_LLAMADAS_TOTAL:
                res, tope_llegado = {"error": "Ya no hay más consultas. Entrega la tarjeta con lo que tienes."}, True
            elif c["nombre"] == "medir_lo_prometido" and sam >= MAX_LLAMADAS_SAM:
                res = {"error": f"SAM ya se usó {MAX_LLAMADAS_SAM} veces. Entrega la tarjeta con lo que tienes."}
            else:
                consultas += consulta
                sam += c["nombre"] == "medir_lo_prometido"
                try:
                    res = {"error": "Los argumentos no eran JSON válido."} if "_invalidos" in args else caja.correr(c["nombre"], args)
                except meta_api.TopeAlcanzado:
                    raise
                except Exception as e:  # noqa: BLE001 — una herramienta que falla se le dice al modelo y sigue
                    res = {"error": f"La herramienta falló: {type(e).__name__}"}
            traza.append({"turno": turno, "herramienta": c["nombre"], "args": args if c["nombre"] != "entregar_tarjeta" else "…",
                          "resultado": res if c["nombre"] == "entregar_tarjeta" else f"{len(json.dumps(res))} caracteres"})
            conv.devolver(c["id"], res)
            if c["nombre"] == "entregar_tarjeta" and res.get("aceptada"):
                tarjeta = args
        if tarjeta:
            return tarjeta, traza, None
        if tope_llegado:
            conv.insistir()  # sin más consultas: que cierre con lo que tiene
    return None, traza, None


def investigar(caja, motores: tuple, fabricas: dict) -> tuple[dict | None, list, str | None, list]:
    """Corre el ciclo con cada motor en orden hasta que uno cierre. Devuelve la tarjeta (o None), la traza
    con el motor de cada paso, qué motor la escribió y las fallas."""
    traza, fallas = [], []
    for motor in motores:
        tarjeta, pasos, falla = ciclo(caja, fabricas[motor]())
        traza += [{"motor": motor, **p} for p in pasos]
        if falla:
            fallas.append(f"{motor}: {falla}")
        if tarjeta:
            return tarjeta, traza, motor, fallas
    return None, traza, None, fallas


def inicio_del_agente(video: dict, idioma: str = "es") -> str:
    en = " Escribe la tarjeta en inglés." if idioma == "en" else ""
    return f"Revisa el arranque de este video de {video['duracion_s']:.0f} s y entrega la tarjeta.{en}"


def correr_agente(carpeta: Path, modelo: Modelo, voz: dict, motor: str = "", nombre: str = "agente.json", idioma: str = "es") -> dict:
    motor = motor or explicar.motor_por_omision()
    sufijo = "" if motor == "api" else "-" + motor.replace("+", "-y-")
    caja = Caja(carpeta, modelo, voz)
    v = caja.resultado["video"]
    inicio = inicio_del_agente(v, idioma)
    fabricas = {m: (lambda m=m: CONVERSADORES[m](inicio)) for m in MOTORES[motor]}
    tarjeta, traza, quien, fallas = investigar(caja, MOTORES[motor], fabricas)
    if tarjeta is None:  # ningún ciclo cerró: una sola vuelta de «explicar», con su propio validador
        tarjeta = explicar.explicar(carpeta, caja.resultado["arranque"], motor, f"explicar{sufijo}.json", idioma)
        modelo_, servido, fuente = tarjeta["licencia"]["modelo"], tarjeta["licencia"]["servido_por"], "explicar (respaldo)"
    else:
        modelo_, servido, fuente = CONVERSADORES[quien].modelo, CONVERSADORES[quien].servido_por, "agente"
    tarjeta["licencia"] = {"modelo": modelo_, "servido_por": servido, "instrucciones": "skills/agente.md (agente-v3)",
                           "fuente": fuente, "motor": motor, "rescate": bool(quien) and quien != MOTORES[motor][0],
                           "turnos": len({(t["motor"], t["turno"]) for t in traza}), "traza": traza,
                           "falla": "; ".join(fallas) or None}
    (carpeta / nombre).write_text(json.dumps(tarjeta, ensure_ascii=False, indent=1), encoding="utf-8")
    return tarjeta


def cargar_voz(ruta: Path) -> dict:
    voz = {}
    for l in ruta.open(encoding="utf-8"):
        d = json.loads(l); voz[d["codigo"]] = d["tramos"]
    return voz


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("carpeta", type=Path)
    ap.add_argument("--modelo", type=Path, required=True)
    ap.add_argument("--voz", type=Path, required=True)
    ap.add_argument("--motor", choices=list(MOTORES), default="",
                    help="api: Spark 1.3 · abierto: Muse Spark Open en Baseten · abierto+api: Spark Open con rescate de Spark 1.3.")
    a = ap.parse_args()
    t = correr_agente(a.carpeta, Modelo.cargar(a.modelo), cargar_voz(a.voz), a.motor)
    print(json.dumps({k: t.get(k) for k in ("por_que", "lo_bueno", "lo_flojo", "que_cambiar", "mejoras_opcionales",
                                            "momento_s", "confianza")}, ensure_ascii=False, indent=1))
    print(f"{t['licencia']['fuente']} · {t['licencia']['modelo']} · {t['licencia']['turnos']} turnos · " +
          " → ".join(x.get("herramienta", "texto") for x in t["licencia"]["traza"]))


if __name__ == "__main__":
    main()
