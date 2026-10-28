"""Orquestador de Retina: un video -> resultado.json para el panel.

Orden: segmentar -> embeber (V-JEPA 2 local) -> predecir la curva -> riesgo del
arranque -> [con API: transcribir -> describir -> el agente explica el arranque (o
«explicar» de una vuelta si no hay --voz)]. Cada paso guarda su salida en la
carpeta del caso. Lo gratuito (curva y riesgo) se escribe primero: si un paso de
la API falla, el resultado se queda con lo que sí corrió y la «licencia» dice qué
no se pudo revisar. El storyboard no corre aquí: cuesta y necesita aprobación
(retina.storyboard --aprobar).

Retina está hecha para revisar un video ANTES de publicarlo. Para quien lo use
con contenido de una empresa hay un candado: con RETINA_SOLO_PUBLICADOS=1 (lo
que viene por omisión) a la API de Meta solo van videos ya publicados y hay que
confirmarlo con --ya-publicado. Un creador con su propio video lo apaga con
RETINA_SOLO_PUBLICADOS=0 en su .env.

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
from .curvas import cubeta
from .segmentar import segmentar

# Lo que se paga y depende del video: si el video cambia, se borra para no explicar otro.
PAGADO = ("transcribir.json", "describir.json", "explicar.json", "agente.json", "sam.json", "primeros-3s.mp4")


def solo_publicados() -> bool:
    """El candado se lee después del .env; encendido salvo que se apague con un 0."""
    meta_api._cargar_env()
    return os.environ.get("RETINA_SOLO_PUBLICADOS", "1").strip() != "0"


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
           titulo: str, con_api: bool, arranque: Path, ver_video: bool = True, voz: Path | None = None,
           publicado: bool = False) -> dict:
    if con_api and not publicado and solo_publicados():
        raise ValueError("El candado está encendido: a la API de Meta solo van videos ya publicados. "
                         "Confírmalo con --ya-publicado, o apágalo con RETINA_SOLO_PUBLICADOS=0 si el video es tuyo.")
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

    from .predecir import Modelo
    v = {"fecha": datetime.strptime(fecha, "%Y-%m-%d %H:%M"), "dur": man["duracion_s"], "codigo": codigo,
         "talento": talento.upper().strip(), "archivo": titulo}
    v["cubeta"] = cubeta(v["dur"])
    m = Modelo.cargar(modelo)
    t = time.time(); pred = m.predecir(v, emb, audio); tiempos["predecir"] = round(time.time() - t, 1)

    from .arranque import Arranque
    riesgo_arranque = Arranque.cargar(arranque).predecir(v, np.array(pred["curva_parecidos"]))

    resultado = {
        "version": "retina-v1",
        "video": {"duracion_s": man["duracion_s"], "codigo": codigo, "talento": talento, "titulo": titulo},
        "prediccion": pred,
        "arranque": riesgo_arranque,
        "explicacion": None,
        "tiempos_s": tiempos,
        "licencia": {
            "comparado_con": f"{pred['n_parecidos']:,} videos " + {
                "cubeta+talento 90 d": "del mismo talento y duración de los últimos 90 días",
                "cubeta 90 d": "de la misma duración de los últimos 90 días",
                "cubeta+talento": "del mismo talento y duración",
                "cubeta": "de la misma duración",
            }.get(pred["regla_de_parecidos"], "publicados"),
            "regla": pred["regla_de_parecidos"],
            "datos_hasta": pred["datos_hasta"],
            "vio_el_video": pred["uso_video"],
            "no_pude_revisar": no_pude,
        },
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
        if not (salida / "transcribir.json").exists():
            _paso("transcribir", tiempos, no_pude, "La voz y los silencios", transcribir.transcribir, salida)
        if not (salida / "describir.json").exists():
            _paso("describir", tiempos, no_pude, "Lo que se ve tramo a tramo", describir.describir, salida)
        if (salida / "describir.json").exists():
            if voz is not None:  # el agente lee resultado.json: por eso va después de escribirlo
                from .agente import cargar_voz, correr_agente
                resultado["explicacion"] = _paso("agente", tiempos, no_pude, "Por qué y qué cambiar en el arranque",
                                                 correr_agente, salida, m, cargar_voz(voz))
            else:
                resultado["explicacion"] = _paso("explicar", tiempos, no_pude, "Por qué y qué cambiar en el arranque",
                                                 explicar.explicar, salida, riesgo_arranque)
        else:
            no_pude.append("Por qué y qué cambiar en el arranque (no hubo descripción del video).")
    no_pude.append("La música: no se analiza la letra ni la licencia.")
    escribir()
    return resultado


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("video", type=Path)
    ap.add_argument("--modelo", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--codigo", default="BORRADOR")
    ap.add_argument("--talento", default="")
    ap.add_argument("--fecha", default=datetime.now().strftime("%Y-%m-%d %H:%M"))
    ap.add_argument("--titulo", default="")
    ap.add_argument("--con-api", action="store_true", help="Usa la Meta Model API (cuesta).")
    ap.add_argument("--ya-publicado", action="store_true", help="Confirma que el video ya está publicado (lo pide el candado RETINA_SOLO_PUBLICADOS=1).")
    ap.add_argument("--arranque", type=Path, required=True, help="Modelo del riesgo del arranque (JSON de retina.arranque).")
    ap.add_argument("--voz", type=Path, help="Voz de la historia (voz.jsonl): activa el agente en lugar de explicar.")
    a = ap.parse_args()
    r = correr(a.video, a.modelo, a.salida, a.codigo, a.talento, a.fecha, a.titulo, a.con_api, a.arranque,
               voz=a.voz, publicado=a.ya_publicado)
    print(f"Riesgo del arranque: {r['arranque']['nivel']} · {r['tiempos_s']}")
    for x in r["licencia"]["no_pude_revisar"]:
        print(f"  no revisé: {x}")


if __name__ == "__main__":
    main()
