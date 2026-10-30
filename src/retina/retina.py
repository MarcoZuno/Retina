"""Orquestador de Retina: un video -> resultado.json para el panel.

Orden: segmentar -> embeber (V-JEPA 2 local) -> predecir la curva -> riesgo del
arranque -> [con API: transcribir -> describir -> el agente explica el arranque (o
«explicar» de una vuelta si no hay --voz)]. Cada paso guarda su salida en la
carpeta del caso. Lo gratuito (curva y riesgo) se escribe primero: si un paso de
la API falla, el resultado se queda con lo que sí corrió y la «licencia» dice qué
no se pudo revisar. El storyboard no corre aquí: cuesta y necesita aprobación
(retina.storyboard --aprobar).

Retina está hecha para revisar un video ANTES de publicarlo: por omisión, cualquier
video va a la API de Meta. Una empresa que no quiera mandar borradores prende el
candado con RETINA_SOLO_PUBLICADOS=1 en su .env: entonces solo van videos ya
publicados y hay que confirmarlo con --ya-publicado.

Uso:
    python -m retina.retina VIDEO.mp4 --modelo MODELO.pkl --arranque ARRANQUE.json --salida CARPETA \
        --codigo NOTB0000 --talento "NOMBRE" --fecha "2026-10-28 18:00" --titulo "..." \
        [--con-api --ya-publicado [--voz VOZ.jsonl]]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from . import meta_api
from .curvas import cubeta, tramo_exceso
from .segmentar import Aviso, segmentar

# Lo que se paga y depende del video: si el video cambia, se borra para no explicar otro.
PAGADO = ("transcribir.json", "describir.json", "explicar.json", "agente.json", "sam.json", "primeros-3s.mp4")


def solo_publicados() -> bool:
    """El candado se lee después del .env; apagado salvo que se prenda con un 1."""
    meta_api._cargar_env()
    return os.environ.get("RETINA_SOLO_PUBLICADOS", "0").strip() == "1"


def huella(video: Path) -> str:
    h = hashlib.sha256()
    with video.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def preparar_carpeta(video: Path, salida: Path) -> None:
    """Reusa lo ya pagado solo si es del mismo video (misma huella)."""
    salida.mkdir(parents=True, exist_ok=True)
    nueva, archivo = huella(video), salida / "huella.txt"
    if archivo.exists() and archivo.read_text(encoding="utf-8").strip() != nueva:
        for nombre in PAGADO:
            (salida / nombre).unlink(missing_ok=True)
    archivo.write_text(nueva, encoding="utf-8")


def solo_modelos_meta() -> bool:
    """Plan B (29-oct): si los organizadores dicen que una fórmula ajustada (la ridge) cuenta como modelo
    que no es de Meta, RETINA_SOLO_MODELOS_META=1 la apaga. La curva queda en el promedio de videos de su
    duración, no hay nivel de riesgo y la tarjeta sale solo de lo que ven los modelos de Meta."""
    meta_api._cargar_env()
    return os.environ.get("RETINA_SOLO_MODELOS_META", "0").strip() == "1"


def sin_formula(pred: dict) -> dict:
    base = np.array(pred["curva_parecidos"])
    t = tramo_exceso(base, base)
    caida = round(float((base[t] - base[t + 1]) * 100), 1)
    return {**pred, "curva_predicha": pred["curva_parecidos"], "tramo_riesgo": t, "caida_predicha_pp": caida,
            "caida_parecidos_pp": caida, "cerebro": "promedio", "uso_voz": False, "uso_video": False, "sin_formula": True}


def sin_nivel(pred: dict) -> dict:
    from .predecir import caidas
    from .voz import BLOQUES, NOMBRES_BLOQUES, bloques
    b = bloques(caidas(np.array(pred["curva_parecidos"])))
    return {"nivel": "sin_nivel", "exceso_arranque_pp": 0.0,
            "bloques": [{"bloque": NOMBRES_BLOQUES[i], "tramos": list(BLOQUES[i]),
                         "caida_parecidos_pp": round(float(b[i]) * 100, 1)} for i in range(len(BLOQUES))],
            "uso_voz": False, "entrenado_con": 0, "comparado_con_su_tipo": False, "sin_formula": True}


SIN_NIVEL_NI_NUMERO = {"nivel": "sin_nivel", "exceso_arranque_pp": 0.0, "bloques": [], "uso_voz": False,
                       "entrenado_con": None, "comparado_con_su_tipo": False, "sin_formula": True}


def es_vertical(salida: Path) -> float:
    """Un reel es vertical; basta el primer cuadro (segmentar conserva la proporción)."""
    cuadro = next(iter(sorted((salida / "cuadros").glob("c*.jpg"))), None)
    datos = cuadro.read_bytes() if cuadro else b""
    i = 2  # el tamaño va en el encabezado SOF del JPEG; así no hace falta otra dependencia
    while i + 9 < len(datos) and datos[i] == 0xFF:
        if datos[i + 1] in (0xC0, 0xC1, 0xC2):
            alto, ancho = int.from_bytes(datos[i + 5:i + 7], "big"), int.from_bytes(datos[i + 7:i + 9], "big")
            return float(alto > ancho)
        i += 2 + int.from_bytes(datos[i + 2:i + 4], "big")
    return 0.0


def tramos_de_voz(salida: Path) -> list[list] | None:
    """Lo que se dice según Voice Transcribe, como [[inicio_s, texto], …]."""
    ruta = salida / "transcribir.json"
    if not ruta.exists():
        return None
    turnos = json.loads(ruta.read_text(encoding="utf-8")).get("turnos") or []
    return [[t["startMs"] / 1000, t["transcript"]] for t in turnos if t.get("transcript")] or None


def licencia(pred: dict | None, no_pude: list) -> dict:
    if pred is None:  # sin cerebro: no hay número ni contra qué comparar
        return {"comparado_con": None, "regla": None, "n_parecidos": None, "datos_hasta": None, "vio_el_video": False,
                "conoce_al_creador": False, "cerebro": "ninguno", "sin_formula": True, "no_pude_revisar": no_pude}
    return {
        "comparado_con": (f"{pred['n_parecidos']:,} videos " if pred.get("n_parecidos") is not None else "videos ") + {
            "cubeta+talento 90 d": "del mismo talento y duración de los últimos 90 días",
            "cubeta 90 d": "de la misma duración de los últimos 90 días",
            "cubeta+talento": "del mismo talento y duración",
            "cubeta": "de la misma duración",
            "publica": "de la misma duración en una página grande de Facebook en México",
        }.get(pred["regla_de_parecidos"], "publicados"),
        "regla": pred["regla_de_parecidos"],
        "n_parecidos": pred["n_parecidos"],
        "datos_hasta": pred["datos_hasta"],
        "vio_el_video": pred["uso_video"],
        "sin_formula": bool(pred.get("sin_formula")),
        "formato_poco_conocido": bool(pred.get("formato_poco_conocido")),
        "otro_idioma": bool(pred.get("otro_idioma")),
        "conoce_al_creador": pred.get("conoce_al_creador", True),
        "cerebro": pred.get("cerebro", "casa"),
        "no_pude_revisar": no_pude,
    }


def _paso(nombre: str, tiempos: dict, no_pude: list, que: str, funcion, *args):
    """Corre un paso de la API; si falla, lo anota y sigue con lo demás."""
    t = time.time()
    try:
        salida = funcion(*args)
        tiempos[nombre] = round(time.time() - t, 1)
        return salida
    except Exception as e:  # noqa: BLE001 — cualquier falla de un paso no debe tumbar la revisión
        no_pude.append(f"{que} (falló: {type(e).__name__}).")
        return None


def correr(video: Path, modelo: Path, salida: Path, codigo: str, talento: str, fecha: str,
           titulo: str, con_api: bool, arranque: Path | None, ver_video: bool = True, voz: Path | None = None,
           publicado: bool = False, motor: str = "", idioma: str = "es") -> dict:
    if con_api and not publicado and solo_publicados():
        raise Aviso("candado", "El candado está encendido: a la API de Meta solo van videos ya publicados. "
                               "Marca «ya publicado», o apágalo con RETINA_SOLO_PUBLICADOS=0 si el video es tuyo.")
    tiempos, no_pude = {}, []
    preparar_carpeta(video, salida)
    t = time.time(); man = segmentar(video, salida); tiempos["segmentar"] = round(time.time() - t, 1)

    emb = audio = None
    if ver_video:
        try:
            from .embeber import Embebedor, cuadros_y_audio
            t = time.time()
            marcos, audio = cuadros_y_audio(video)
            emb = Embebedor()(marcos)
            tiempos["embeber"] = round(time.time() - t, 1)
            np.save(salida / "vectores.npy", emb); np.save(salida / "audio.npy", audio)
        except Exception as e:  # noqa: BLE001 — sin GPU o sin V-JEPA 2, la curva sale solo de metadatos
            emb = audio = None
            no_pude.append(f"Lo que pasa en pantalla tramo a tramo con V-JEPA 2 ({type(e).__name__}).")

    from .publico import cargar_modelo
    v = {"fecha": datetime.strptime(fecha, "%Y-%m-%d %H:%M"), "dur": man["duracion_s"], "codigo": codigo,
         "talento": talento.upper().strip(), "archivo": titulo, "titulo": titulo, "reel": es_vertical(salida)}
    v["cubeta"] = cubeta(v["dur"])
    # .json = cerebro público (sin datos de nadie); .pkl = modelo privado de la casa; sin archivo = sin número
    m = cargar_modelo(modelo) if modelo and Path(modelo).is_file() else None
    plan_b = solo_modelos_meta()
    pred = None
    if m is not None:
        t = time.time(); pred = m.predecir(v, emb, audio); tiempos["predecir"] = round(time.time() - t, 1)
        if plan_b:
            pred = sin_formula(pred)
    else:
        no_pude.append("El número: esta copia de Retina no trae el cerebro público (modelos/retina-publico.json).")

    if m is None:
        riesgo_arranque = dict(SIN_NIVEL_NI_NUMERO)
    elif plan_b:
        riesgo_arranque = sin_nivel(pred)
    else:
        from .arranque import Arranque
        arr = Arranque.cargar(arranque) if arranque else m.arranque()  # el público trae su propio riesgo
        riesgo_arranque = arr.predecir(v, np.array(pred["curva_parecidos"]))
        if not getattr(m, "semaforo", True):  # solo se muestra donde está medido (el público: no, ver publico.py)
            riesgo_arranque = {**riesgo_arranque, "nivel": "sin_nivel"}

    resultado = {
        "version": "retina-v1",
        "idioma": idioma,
        "video": {"duracion_s": man["duracion_s"], "codigo": codigo, "talento": talento, "titulo": titulo},
        "prediccion": pred,
        "arranque": riesgo_arranque,
        "explicacion": None,
        "tiempos_s": tiempos,
        "licencia": licencia(pred, no_pude),
    }

    def escribir() -> None:
        (salida / "resultado.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")

    escribir()  # lo gratuito queda aunque la API falle después
    if not con_api:
        no_pude.append("Por qué y qué cambiar en el arranque (se corrió sin la API de Meta).")
        no_pude.append("La voz y los silencios (se corrió sin la API de Meta).")
    else:
        from . import describir, explicar, transcribir
        # Si el caso ya trae la transcripción o la descripción del mismo video, se reusan: cuestan.
        if not man.get("audio"):
            no_pude.append("La voz y los silencios: el video no trae audio. Lo de abajo sale solo de lo que se ve.")
        elif not (salida / "transcribir.json").exists():
            _paso("transcribir", tiempos, no_pude, "La voz y los silencios", transcribir.transcribir, salida,
                  transcribir.idioma_de(titulo))
        voz_json = salida / "transcribir.json"
        hasta_s = json.loads(voz_json.read_text(encoding="utf-8")).get("escucho_hasta_s") if voz_json.exists() else None
        if hasta_s:
            no_pude.append(f"La voz después del minuto {int(hasta_s // 60)}: Voice Transcribe escucha hasta ahí, "
                           "y el arranque queda completo.")
        tramos = tramos_de_voz(salida)
        # Cómo arranca, según Muse Spark Open (táctica del gancho, claridad, curiosidad). Se muestra siempre y,
        # si el cerebro público la aprendió, también entra al número.
        from .ficha import ficha_de
        resultado["ficha"] = _paso("ficha", tiempos, no_pude, "Cómo arranca (ficha de Muse Spark Open)",
                                   ficha_de, titulo, tramos)
        if tramos and m is not None and not m.de_la_casa(v) and not plan_b:
            # Video de fuera: con la voz ya se puede usar el cerebro para cualquier video.
            pred = m.predecir(v, emb, audio, tramos, resultado["ficha"])
            # Retina aprendió las palabras en español: con otro idioma el número es una referencia más débil.
            dichas = " ".join(x for _, x in tramos).split()[:60]
            pred["otro_idioma"] = transcribir.idioma_de(titulo + " " + " ".join(dichas)) == "en"
            resultado["prediccion"], resultado["licencia"] = pred, licencia(pred, no_pude)
            escribir()
        if not (salida / "describir.json").exists():
            _paso("describir", tiempos, no_pude, "Lo que se ve tramo a tramo",
                  lambda c: describir.describir(c, idioma=idioma), salida)
        if (salida / "describir.json").exists():
            if voz is not None and m is not None and m.filas:  # el agente lee resultado.json y busca en la historia de la casa
                from .agente import cargar_voz, correr_agente
                resultado["explicacion"] = _paso("agente", tiempos, no_pude, "Por qué y qué cambiar en el arranque",
                                                 correr_agente, salida, m, cargar_voz(voz), motor)
            else:
                # Sin agente, SAM revisa igual si lo que promete el título se ve en los primeros 3 segundos.
                from .sam import medir_promesa
                _paso("sam", tiempos, no_pude, "Si lo que promete el título se ve al inicio (SAM 3.1)",
                      medir_promesa, salida, titulo)
                resultado["explicacion"] = _paso("explicar", tiempos, no_pude, "Por qué y qué cambiar en el arranque",
                                                 explicar.explicar, salida, riesgo_arranque, motor, "explicar.json", idioma)
        else:
            no_pude.append("Por qué y qué cambiar en el arranque (no hubo descripción del video).")
        if (salida / "describir.json").exists():
            # Lo que Meta recomienda para los primeros segundos, calculado en código (no llama a la API).
            from .revision_meta import revisar
            resultado["revision_meta"] = _paso("revision_meta", tiempos, no_pude,
                                               "Las recomendaciones de Meta para el inicio", revisar, salida, idioma) or []
    no_pude.append("La música: no se analiza la letra ni la licencia.")
    escribir()
    return resultado


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("video", type=Path)
    ap.add_argument("--modelo", type=Path, default=Path(__file__).resolve().parents[2] / "modelos" / "retina-publico.json",
                    help="Por omisión, el cerebro público. Un .pkl es el modelo privado de una empresa.")
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--codigo", default="BORRADOR")
    ap.add_argument("--talento", default="")
    ap.add_argument("--fecha", default=datetime.now().strftime("%Y-%m-%d %H:%M"))
    ap.add_argument("--titulo", default="")
    ap.add_argument("--con-api", action="store_true", help="Usa la Meta Model API (cuesta).")
    ap.add_argument("--ya-publicado", action="store_true", help="Confirma que el video ya está publicado (lo pide el candado RETINA_SOLO_PUBLICADOS=1).")
    ap.add_argument("--arranque", type=Path, help="Modelo del riesgo del arranque (JSON de retina.arranque). "
                    "Con el cerebro público (modelos/retina-publico.json) no hace falta: ya lo trae.")
    ap.add_argument("--voz", type=Path, help="Voz de la historia (voz.jsonl): activa el agente en lugar de explicar.")
    ap.add_argument("--motor", default="", choices=["", "api", "abierto", "abierto+api"],
                    help="Quién escribe la tarjeta: api (Spark 1.3), abierto (Muse Spark Open) o abierto+api "
                         "(Spark Open con rescate de Spark 1.3). Por omisión, RETINA_MOTOR del .env.")
    ap.add_argument("--idioma", default="es", choices=["es", "en"], help="Idioma de la tarjeta.")
    a = ap.parse_args()
    r = correr(a.video, a.modelo, a.salida, a.codigo, a.talento, a.fecha, a.titulo, a.con_api, a.arranque,
               voz=a.voz, publicado=a.ya_publicado, motor=a.motor, idioma=a.idioma)
    print(f"Riesgo del arranque: {r['arranque']['nivel']} · {r['tiempos_s']}")
    for x in r["licencia"]["no_pude_revisar"]:
        print(f"  no revisé: {x}")


if __name__ == "__main__":
    main()
