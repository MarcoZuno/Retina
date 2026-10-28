"""Retina como agente: Spark investiga el arranque con herramientas y entrega la tarjeta.

El patrón de las recetas de Meta: el código calcula, el modelo interpreta y un
validador revisa. Las herramientas solo leen lo que ya calcularon las
estaciones (describir, transcribir, el riesgo del arranque y la historia de
videos parecidos). La tarjeta se entrega con `entregar_tarjeta`, y el mismo
validador de «explicar» la revisa dentro del ciclo: si falla, Spark recibe los
problemas y corrige. Guardas: tope de turnos, llamadas repetidas y el tope de
gasto del proyecto. Si el ciclo no cierra, cae a «explicar» de una sola vuelta.

Uso:
    python -m retina.agente CARPETA --modelo MODELO.pkl --voz VOZ.jsonl
        (CARPETA ya trae resultado.json, describir.json y transcribir.json)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import timedelta
from pathlib import Path

from . import explicar, meta_api
from .curvas import cubeta, regla_de_hoy
from .esquemas import RAIZ
from .predecir import Modelo, caidas
from .voz import BLOQUES, bloques

MODELO = "muse-spark-1.3"
MAX_TURNOS = 10
REPETIDAS = 2  # la misma llamada con los mismos datos, más de esto, corta el ciclo


def _herramienta(nombre: str, descripcion: str, props: dict) -> dict:
    return {"type": "function", "name": nombre, "description": descripcion,
            "parameters": {"type": "object", "additionalProperties": False, "properties": props, "required": list(props)}}


RANGO = {"desde_s": {"type": "number"}, "hasta_s": {"type": "number"}}
HERRAMIENTAS = [
    _herramienta("ver_arranque", "Nivel de riesgo del arranque, dónde terminan el gancho y el primer cuarto, "
                 "y cuánta gente se va en videos parecidos en cada parte.", {}),
    _herramienta("ver_tramos", "Lo que se ve en pantalla entre dos segundos: qué pasa, texto en pantalla, "
                 "plano, cambios de plano, presentador.", RANGO),
    _herramienta("oir", "Lo que se dice entre dos segundos (frases con su segundo) y los silencios de 3 s o más.", RANGO),
    _herramienta("buscar_parecidos", "Cómo arrancan videos parecidos ya publicados (misma duración y, si hay, mismo "
                 "talento): su título y lo que dicen en el arranque. «buenos» = retuvieron mejor que sus parecidos; "
                 "«malos» = perdieron más.",
                 {"cuales": {"type": "string", "enum": ["buenos", "malos"]}, "n": {"type": "integer"}}),
    _herramienta("entregar_tarjeta", "Entrega la tarjeta final. El código la revisa; si devuelve problemas, corrige y "
                 "vuelve a entregar.", explicar.esquema()["properties"]),
]


def titulo_limpio(archivo: str, codigo: str) -> str:
    t = re.sub(r"\d{4}-\d{2}-\d{2}", " ", archivo.replace(codigo, " "))
    return re.sub(r"\s+", " ", re.sub(r"\.mp4$", "", t, flags=re.I)).strip()


class Caja:
    """Lo que las herramientas pueden leer de un caso. Nada se escribe."""

    def __init__(self, carpeta: Path, modelo: Modelo, voz: dict):
        self.carpeta, self.modelo, self.voz = carpeta, modelo, voz
        self.resultado = json.loads((carpeta / "resultado.json").read_text(encoding="utf-8"))
        self.datos = explicar.datos_del_arranque(carpeta, self.resultado["arranque"])
        self.vistos: list = []

    def ver_arranque(self) -> dict:
        d = self.datos
        return {k: d[k] for k in ("duracion_video_s", "gancho_s", "primer_cuarto_s", "nivel_de_riesgo",
                                  "perdida_extra_predicha_pp", "caida_de_videos_parecidos_pp")}

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

    def correr(self, nombre: str, args: dict) -> dict:
        if nombre == "entregar_tarjeta":
            faltan = [k for k in explicar.esquema()["required"] if k not in args]
            if faltan:
                return {"aceptada": False, "problemas": [f"faltan campos: {', '.join(faltan)}"]}
            problemas = explicar.revisar(args, {**self.datos, "vistos": self.vistos})
            return {"aceptada": not problemas, "problemas": problemas}
        salida = getattr(self, nombre)(**args)
        self.vistos.append(salida)
        return salida


def instrucciones() -> str:
    return (RAIZ / "skills" / "agente.md").read_text(encoding="utf-8").split("---", 2)[2].strip()


def correr_agente(carpeta: Path, modelo: Modelo, voz: dict) -> dict:
    caja = Caja(carpeta, modelo, voz)
    v = caja.resultado["video"]
    conversacion = [{"type": "message", "role": "user", "content": [{"type": "input_text", "text":
                     f"Revisa el arranque de este video de {v['duracion_s']:.0f} s y entrega la tarjeta."}]}]
    traza, cuenta, tarjeta = [], {}, None
    for turno in range(1, MAX_TURNOS + 1):
        r = meta_api.responder("agente", {
            "model": MODELO, "instructions": instrucciones(), "input": conversacion, "tools": HERRAMIENTAS,
            "parallel_tool_calls": False, "store": False, "reasoning": {"effort": "medium"},
            "max_output_tokens": 6000, "prompt_cache_key": "retina-agente-v1"})
        salida = r.get("output", [])
        conversacion += [x for x in salida if x.get("type") != "reasoning"]  # sin store no se reenvía el razonamiento
        llamadas = [x for x in salida if x.get("type") == "function_call"]
        if not llamadas:
            traza.append({"turno": turno, "texto": meta_api.texto_de(r)[:300]})
            conversacion.append({"type": "message", "role": "user", "content": [{"type": "input_text",
                                 "text": "Entrega la tarjeta con entregar_tarjeta."}]})
            continue
        for c in llamadas:
            args = json.loads(c.get("arguments") or "{}")
            huella = hashlib.sha1(f"{c['name']}{json.dumps(args, sort_keys=True)}".encode()).hexdigest()
            cuenta[huella] = cuenta.get(huella, 0) + 1
            if cuenta[huella] > REPETIDAS:
                res = {"error": "Ya hiciste esta misma llamada. Usa lo que ya tienes y entrega la tarjeta."}
            else:
                try:
                    res = caja.correr(c["name"], args)
                except (AttributeError, TypeError, KeyError) as e:
                    res = {"error": f"Llamada inválida: {type(e).__name__}"}
            traza.append({"turno": turno, "herramienta": c["name"], "args": args if c["name"] != "entregar_tarjeta" else "…",
                          "resultado": res if c["name"] == "entregar_tarjeta" else f"{len(json.dumps(res))} caracteres"})
            conversacion.append({"type": "function_call_output", "call_id": c["call_id"],
                                 "output": json.dumps(res, ensure_ascii=False)})
            if c["name"] == "entregar_tarjeta" and res.get("aceptada"):
                tarjeta = args
        if tarjeta:
            break
    fuente = "agente"
    if tarjeta is None:  # el ciclo no cerró: una sola vuelta de «explicar», con su propio validador
        tarjeta, fuente = explicar.explicar(carpeta, caja.resultado["arranque"]), "explicar (respaldo)"
    tarjeta["licencia"] = {"modelo": MODELO, "instrucciones": "skills/agente.md (agente-v1)", "fuente": fuente,
                           "turnos": len({t["turno"] for t in traza}), "traza": traza}
    (carpeta / "agente.json").write_text(json.dumps(tarjeta, ensure_ascii=False, indent=1), encoding="utf-8")
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
    a = ap.parse_args()
    t = correr_agente(a.carpeta, Modelo.cargar(a.modelo), cargar_voz(a.voz))
    print(json.dumps({k: t.get(k) for k in ("por_que", "que_cambiar", "momento_s", "confianza")}, ensure_ascii=False, indent=1))
    print(f"{t['licencia']['fuente']} · {t['licencia']['turnos']} turnos · " +
          " → ".join(x.get("herramienta", "texto") for x in t["licencia"]["traza"]))


if __name__ == "__main__":
    main()
