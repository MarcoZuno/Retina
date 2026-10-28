"""Orquestador de Retina: un borrador -> resultado.json para el panel.

Orden: segmentar -> embeber (V-JEPA 2 local) -> predecir la curva -> riesgo del
arranque -> [con API: transcribir -> describir -> el agente explica el arranque (o
«explicar» de una vuelta si no hay --voz)]. Cada paso guarda su
salida en la carpeta del caso; si un paso no corre, la «licencia» del
resultado dice qué no se pudo revisar. El storyboard no corre aquí: cuesta y
necesita aprobación (retina.storyboard --aprobar).

Uso:
    python -m retina.retina VIDEO.mp4 --modelo MODELO.pkl --salida CARPETA \
        --codigo NOTB0000 --talento "NOMBRE" --fecha "2026-10-28 18:00" --titulo "..." [--con-api [--voz VOZ.jsonl]]
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from .curvas import cubeta
from .segmentar import segmentar


def correr(video: Path, modelo: Path, salida: Path, codigo: str, talento: str, fecha: str,
           titulo: str, con_api: bool, arranque: Path, ver_video: bool = True, voz: Path | None = None) -> dict:
    tiempos, no_pude = {}, []
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
        except ImportError:
            no_pude.append("Lo que pasa en pantalla tramo a tramo (falta V-JEPA 2 en esta máquina).")

    from .predecir import Modelo
    v = {"fecha": datetime.strptime(fecha, "%Y-%m-%d %H:%M"), "dur": man["duracion_s"], "codigo": codigo,
         "talento": talento.upper().strip(), "archivo": titulo}
    v["cubeta"] = cubeta(v["dur"])
    m = Modelo.cargar(modelo)
    t = time.time(); pred = m.predecir(v, emb, audio); tiempos["predecir"] = round(time.time() - t, 1)

    from .arranque import Arranque
    riesgo_arranque = Arranque.cargar(arranque).predecir(v, np.array(pred["curva_parecidos"]))

    explicacion = None
    if con_api:
        from . import describir, explicar, transcribir
        # Si el caso ya trae la transcripción o la descripción (una corrida anterior), se reusan: cuestan.
        if not (salida / "transcribir.json").exists():
            t = time.time(); transcribir.transcribir(salida); tiempos["transcribir"] = round(time.time() - t, 1)
        if not (salida / "describir.json").exists():
            t = time.time(); describir.describir(salida); tiempos["describir"] = round(time.time() - t, 1)
        if voz is None:
            t = time.time(); explicacion = explicar.explicar(salida, riesgo_arranque); tiempos["explicar"] = round(time.time() - t, 1)
    else:
        no_pude.append("Por qué y qué cambiar en el arranque (se corrió sin la API de Meta).")
        no_pude.append("La voz y los silencios (se corrió sin la API de Meta).")
    no_pude.append("La música: no se analiza la letra ni la licencia.")

    resultado = {
        "version": "retina-v1",
        "video": {"duracion_s": man["duracion_s"], "codigo": codigo, "talento": talento, "titulo": titulo},
        "prediccion": pred,
        "arranque": riesgo_arranque,
        "explicacion": explicacion,
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

    escribir()
    if con_api and voz is not None:  # el agente lee resultado.json, así que va después de escribirlo
        from .agente import cargar_voz, correr_agente
        t = time.time(); resultado["explicacion"] = correr_agente(salida, m, cargar_voz(voz))
        tiempos["agente"] = round(time.time() - t, 1)
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
    ap.add_argument("--arranque", type=Path, required=True, help="Modelo del riesgo del arranque (JSON de retina.arranque).")
    ap.add_argument("--voz", type=Path, help="Voz de la historia (voz.jsonl): activa el agente en lugar de explicar.")
    a = ap.parse_args()
    r = correr(a.video, a.modelo, a.salida, a.codigo, a.talento, a.fecha, a.titulo, a.con_api, a.arranque, voz=a.voz)
    a_ = r["arranque"]
    print(f"Riesgo del arranque: {a_['nivel']} ({a_['exceso_arranque_pp']:+} pp contra videos parecidos) · {r['tiempos_s']}")


if __name__ == "__main__":
    main()
