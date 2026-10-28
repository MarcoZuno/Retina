"""Servicio «storyboard»: sugerencia -> 3 ilustraciones del cambio con Muse Image.

Generar imágenes cuesta (USD 0.01 cada una), así que no corre sin aprobación:
sin --aprobar solo muestra el costo estimado. Con imágenes de referencia
(--estilo, hasta 3) usa /v1/images/edits para mantener el mismo estilo entre
cuadros. Cada PNG lleva en su nombre que es ilustración hecha con IA.

Uso:
    python -m retina.storyboard CARPETA/explicar.json [--estilo REF.png ...] [--aprobar]
"""
from __future__ import annotations

import argparse
import base64
import json
import time
from pathlib import Path

from . import integridad, meta_api

MODELO = "muse-image-1.0"
ESTILO = ("Ilustración editorial plana, colores cálidos, trazo limpio, sin texto, sin logos, "
          "sin personas reales ni caras reconocibles. Cuadro {i} de 3 de un storyboard: ")


def _guardar(datos: dict, destino: Path) -> None:
    destino.write_bytes(base64.b64decode(datos["data"][0]["b64_json"]))


def generar(explicacion: Path, estilo: list[Path], aprobar: bool) -> list[Path]:
    e = json.loads(explicacion.read_text(encoding="utf-8"))
    cuadros = e.get("storyboard", [])[:3]
    if not cuadros:
        print("La explicación no trae storyboard (o no pasó el filtro de integridad).")
        return []
    for c in cuadros:  # el filtro vuelve a correr aquí: el storyboard también es una sugerencia
        if integridad.revisar(c):
            raise RuntimeError(f"Cuadro bloqueado por integridad: {c}")
    print(f"{len(cuadros)} imágenes · costo estimado USD {0.01 * len(cuadros):.2f}")
    if not aprobar:
        print("Sin --aprobar no se genera nada.")
        return []
    refs = [{"image_url": "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()} for p in estilo[:3]]
    salidas = []
    for i, c in enumerate(cuadros, 1):
        prompt = ESTILO.format(i=i) + c
        t0 = time.time()
        if refs:
            r = meta_api._pedir("POST", "/images/edits", json={"model": MODELO, "prompt": prompt, "images": refs, "n": 1})
        else:
            r = meta_api._pedir("POST", "/images/generations", json={
                "model": MODELO, "prompt": prompt, "n": 1, "size": "1024x1792",
                "response_format": "b64_json", "output_format": "png"})
        if r.status_code != 200:
            raise meta_api._error(r)
        meta_api._registrar("storyboard", MODELO, time.time() - t0, meta_api.PRECIO_IMAGEN[MODELO])
        destino = explicacion.with_name(f"{explicacion.stem}-cuadro{i}-ilustracion-ia.png")
        _guardar(r.json(), destino)
        salidas.append(destino)
    return salidas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("explicacion", type=Path)
    ap.add_argument("--estilo", type=Path, action="append", default=[])
    ap.add_argument("--aprobar", action="store_true", help="Aprobación humana del gasto.")
    a = ap.parse_args()
    for p in generar(a.explicacion, a.estilo, a.aprobar):
        print(p)


if __name__ == "__main__":
    main()
