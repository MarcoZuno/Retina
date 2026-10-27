"""Orquestador de Retina: un borrador -> resultado.json para el panel.

Orden: segmentar -> embeber (V-JEPA 2 local) -> predecir -> [con API:
transcribir -> describir -> explicar el tramo de riesgo]. Cada paso guarda su
salida en la carpeta del caso; si un paso no corre, la «licencia» del
resultado dice qué no se pudo revisar. El storyboard no corre aquí: cuesta y
necesita aprobación (retina.storyboard --aprobar).

Uso:
    python -m retina.retina VIDEO.mp4 --modelo MODELO.pkl --salida CARPETA \
        --codigo NOTB0000 --talento "NOMBRE" --fecha "2026-10-28 18:00" --titulo "..." [--con-api]
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
           titulo: str, con_api: bool, arranque: Path | None = None) -> dict:
    tiempos, no_pude = {}, []
    t = time.time(); man = segmentar(video, salida); tiempos["segmentar"] = round(time.time() - t, 1)

    emb = audio = None
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
    t = time.time(); pred = Modelo.cargar(modelo).predecir(v, emb, audio); tiempos["predecir"] = round(time.time() - t, 1)

    explicacion, tramos_voz = None, None
    if con_api:
        from . import describir, explicar, transcribir
        from .voz import de_turnos
        t = time.time(); tr = transcribir.transcribir(salida); tiempos["transcribir"] = round(time.time() - t, 1)
        tramos_voz = de_turnos(tr["turnos"])
        t = time.time(); describir.describir(salida); tiempos["describir"] = round(time.time() - t, 1)
        t = time.time()
        explicacion = explicar.explicar(salida, pred["tramo_riesgo"], pred["caida_predicha_pp"], pred["caida_parecidos_pp"])
        tiempos["explicar"] = round(time.time() - t, 1)
    else:
        no_pude.append("Por qué cae y qué cambiar (se corrió sin la API de Meta).")
        no_pude.append("La voz y los silencios (se corrió sin la API de Meta).")
    no_pude.append("La música: no se analiza la letra ni la licencia.")

    riesgo_arranque = None
    if arranque:
        from .arranque import Arranque
        riesgo_arranque = Arranque.cargar(arranque).predecir(v, np.array(pred["curva_parecidos"]), tramos_voz)

    tramo = man["tramos"][pred["tramo_riesgo"]]
    resultado = {
        "version": "retina-v0",
        "video": {"duracion_s": man["duracion_s"], "codigo": codigo, "titulo": titulo},
        "prediccion": pred,
        "arranque": riesgo_arranque,
        "tramo_riesgo": {"indice": pred["tramo_riesgo"], "inicio_s": tramo["inicio_s"], "fin_s": tramo["fin_s"]},
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
    (salida / "resultado.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
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
    ap.add_argument("--arranque", type=Path, help="Modelo del riesgo del arranque (JSON de retina.arranque).")
    a = ap.parse_args()
    r = correr(a.video, a.modelo, a.salida, a.codigo, a.talento, a.fecha, a.titulo, a.con_api, a.arranque)
    p = r["prediccion"]
    print(f"Tramo de riesgo {p['tramo_riesgo']} ({r['tramo_riesgo']['inicio_s']:.0f}-{r['tramo_riesgo']['fin_s']:.0f} s): "
          f"cae {p['caida_predicha_pp']} pp contra {p['caida_parecidos_pp']} en videos parecidos · {r['tiempos_s']}")


if __name__ == "__main__":
    main()
