"""Piloto: ¿SAM 3.1 encuentra objetos en dibujos de Muse Image?

Es la duda que decide cómo se comprueba la apertura: SAM funciona mejor con fotos y los dibujos de Retina
son ilustraciones. Sin datos de nadie: cinco temas inventados, sin un solo caso de la medición. A cada dibujo
se le pregunta por lo que sí tiene (tiene que encontrarlo) y por algo que no tiene (no debe encontrarlo).

Uso (desde la raíz del repo; el concepto siempre sale de reglas/sam-permitidos-v1.json):
    python eval/sam_en_dibujos.py --salida CARPETA --estilo ilustracion|foto [--aprobar]
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina import meta_api, sam  # noqa: E402
from retina.storyboard import MODELO  # noqa: E402

TEMAS = [("bread", "dog", "Una hogaza de pan recién horneado sobre una mesa de cocina."),
         ("dog", "bridge", "Un perro mestizo sentado en la banqueta de una calle tranquila."),
         ("car", "cake", "Un auto compacto estacionado frente a un taller mecánico."),
         ("bridge", "cat", "Un puente de piedra sobre un río en el campo."),
         ("coffee", "car", "Una taza de café humeante junto a una ventana.")]
ESTILOS = {"ilustracion": "Ilustración editorial plana, colores cálidos, trazo limpio, sin texto, sin logos, sin personas. ",
           "foto": "Fotografía realista, luz natural, sin texto, sin logos, sin personas. "}


def dibujar(prompt: str, destino: Path) -> None:
    meta_api._revisar_tope(meta_api.PRECIO_IMAGEN[MODELO])
    t0 = time.time()
    r = meta_api._pedir("POST", "/images/generations", json={
        "model": MODELO, "prompt": prompt, "n": 1, "size": "1024x1792", "response_format": "b64_json", "output_format": "png"})
    if r.status_code != 200:
        raise meta_api._error(r)
    meta_api._registrar("piloto-sam", MODELO, time.time() - t0, meta_api.PRECIO_IMAGEN[MODELO])
    destino.write_bytes(base64.b64decode(r.json()["data"][0]["b64_json"]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--estilo", choices=list(ESTILOS), required=True)
    ap.add_argument("--aprobar", action="store_true", help="Sin esto solo dice cuánto costaría.")
    a = ap.parse_args()
    costo = len(TEMAS) * (meta_api.PRECIO_IMAGEN[MODELO] + 2 * sam.MIN_CUADROS_COBRADOS * sam.USD_POR_CUADRO)
    print(f"{len(TEMAS)} dibujos y {2 * len(TEMAS)} revisiones · USD {costo:.2f}")
    if not a.aprobar:
        return
    a.salida.mkdir(parents=True, exist_ok=True)
    filas = []
    for objeto, ausente, escena in TEMAS:
        destino = a.salida / f"{a.estilo}-{objeto}.png"
        if not destino.exists():
            dibujar(ESTILOS[a.estilo] + escena, destino)
        filas.append({"objeto": objeto, "lo_encuentra": sam.medir_imagen(destino, objeto),
                      "ausente": ausente, "falsa_alarma": sam.medir_imagen(destino, ausente)})
        print(json.dumps(filas[-1], ensure_ascii=False), flush=True)
    resumen = {"estilo": a.estilo, "encontrados": sum(f["lo_encuentra"].get("aparece", False) for f in filas),
               "falsas_alarmas": sum(f["falsa_alarma"].get("aparece", False) for f in filas), "de": len(filas)}
    (a.salida / f"piloto-{a.estilo}.json").write_text(json.dumps({"resumen": resumen, "filas": filas}, ensure_ascii=False, indent=1),
                                                       encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False))


if __name__ == "__main__":
    main()
