"""Servicio «storyboard»: sugerencia -> 3 ilustraciones del cambio con Muse Image.

Generar imágenes cuesta (USD 0.01 cada una), así que no corre sin aprobación:
sin --aprobar solo muestra el costo estimado. Con imágenes de referencia
(--estilo, hasta 3) usa /v1/images/edits para mantener el mismo estilo entre
cuadros. Cada PNG lleva en su nombre que es ilustración hecha con IA.

Uso:
    python -m retina.storyboard CARPETA/explicar.json [--estilo REF.png ...] [--aprobar]

Si la carpeta trae resultado.json y su tarjeta es la misma, las ilustraciones quedan anotadas
en él (explicacion.storyboard_imagenes) y el panel las muestra.
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


def dibujar_uno(prompt: str, destino: Path, refs: list | None = None, servicio: str = "storyboard") -> None:
    """Una imagen con Muse Image. Con `refs` usa /v1/images/edits para mantener el mismo estilo. Aparta su precio
    antes de llamar, con el candado del tope (meta_api.reservar): dos dibujos a la vez no pasan por el mismo hueco."""
    reserva = meta_api.reservar(servicio, meta_api.PRECIO_IMAGEN[MODELO])
    t0 = time.time()
    # Si _pedir lanza (red, tiempo agotado) no sabemos si la API cobró: la reserva se queda apartada hasta que venza.
    if refs:
        r = meta_api._pedir("POST", "/images/edits", json={"model": MODELO, "prompt": prompt, "images": refs, "n": 1})
    else:
        r = meta_api._pedir("POST", "/images/generations", json={
            "model": MODELO, "prompt": prompt, "n": 1, "size": "1024x1792",
            "response_format": "b64_json", "output_format": "png"})
    if r.status_code != 200:
        meta_api.liberar(reserva)
        raise meta_api._error(r)
    meta_api._registrar(servicio, MODELO, time.time() - t0, meta_api.PRECIO_IMAGEN[MODELO], reserva)
    _guardar(r.json(), destino)


def anotar(carpeta: Path, cuadros: list[str], rutas: list[Path]) -> None:
    """Anota las ilustraciones en el resultado.json del caso para que el panel las muestre, solo si
    son del mismo storyboard que trae su tarjeta (no de otra explicación de la misma carpeta)."""
    ruta = carpeta / "resultado.json"
    if not ruta.exists():
        return
    r = json.loads(ruta.read_text(encoding="utf-8"))
    e = r.get("explicacion") or {}
    if e.get("storyboard", [])[:3] != cuadros:
        return
    e["storyboard_imagenes"] = [p.name for p in rutas]
    ruta.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")


def generar(explicacion: Path, estilo: list[Path], aprobar: bool) -> list[Path]:
    e = json.loads(explicacion.read_text(encoding="utf-8"))
    e = e.get("explicacion") or e  # también acepta el resultado.json del caso
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
    meta_api._revisar_tope(0.01 * len(cuadros))
    refs = [{"image_url": "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()} for p in estilo[:3]]
    salidas = []
    for i, c in enumerate(cuadros, 1):
        nombre = "storyboard" if explicacion.name == "resultado.json" else explicacion.stem
        destino = explicacion.with_name(f"{nombre}-cuadro{i}-ilustracion-ia.png")
        dibujar_uno(ESTILO.format(i=i) + c, destino, refs)
        salidas.append(destino)
    anotar(explicacion.parent, cuadros, salidas)
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
