"""Diagnóstico: ¿por qué SAM 3.1 no encuentra algunos objetos en los dibujos?

Escenas inventadas, sin ningún caso de la medición. Cada objeto se dibuja en ilustración y en foto, con la frase
«Main subject, large and centered» que usa Retina, y SAM lo busca con dos palabras: la de la lista y una más común.
Sirve para saber si falla el dibujo (el objeto no está), SAM (está y no lo ve) o la palabra.

Uso (desde la raíz del repo):
    python eval/sam_objetos_dificiles.py --salida CARPETA [--aprobar]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina import meta_api, sam, storyboard  # noqa: E402

ESTILOS = {"ilustracion": "Ilustración editorial plana, colores cálidos, trazo limpio, sin texto, sin logos, sin personas. ",
           "foto": "Fotografía realista, luz natural, sin texto, sin logos, sin personas. "}
# objeto de la lista, palabra alterna (también de la lista, o None) y escena
OBJETOS = [("vape", "bottle", "Un cigarro electrónico sobre una mesa de madera."),
           ("tortilla", "food", "Una pila de tortillas de maíz recién hechas sobre un comal."),
           ("nopal", "cactus", "Un nopal verde con pencas grandes en un jardín."),
           ("dump", "field", "Un tiradero de basura al aire libre, con bolsas y escombro."),
           ("handkerchief", "fabric", "Un pañuelo azul doblado sobre una mesa."),
           ("fair", "building", "Una feria de pueblo con rueda de la fortuna y puestos de colores."),
           ("coffee", "cup", "Una taza de café de olla sobre una mesa de barro."),
           ("city", "building", "Una ciudad grande vista de lejos, con edificios y avenidas.")]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--aprobar", action="store_true")
    a = ap.parse_args()
    costo = len(OBJETOS) * len(ESTILOS) * (0.01 + 2 * sam.MIN_CUADROS_COBRADOS * sam.USD_POR_CUADRO)
    print(f"USD {costo:.2f}")
    if not a.aprobar:
        return
    a.salida.mkdir(parents=True, exist_ok=True)
    filas = []
    for objeto, alterna, escena in OBJETOS:
        for estilo, prefijo in ESTILOS.items():
            destino = a.salida / f"{estilo}-{objeto}.png"
            if not destino.exists():
                meta_api._revisar_tope(0.01)
                try:
                    storyboard.dibujar_uno(f"{prefijo}{escena} Main subject, large and centered: {objeto}.", destino, servicio="diagnostico")
                except RuntimeError as e:  # Muse Image puede rechazar el pedido: eso también es un hallazgo
                    print(json.dumps({"objeto": objeto, "estilo": estilo, "rechazo_muse_image": str(e)[:80]}, ensure_ascii=False), flush=True)
                    continue
            f = {"objeto": objeto, "estilo": estilo}
            for palabra in dict.fromkeys(x for x in (objeto, alterna) if x):
                r = sam.medir_imagen(destino, palabra)
                f[palabra] = r.get("pct_maximo_del_cuadro", r.get("error")) if r.get("aparece", True) else 0.0
            filas.append(f)
            print(json.dumps(f, ensure_ascii=False), flush=True)
    (a.salida / "diagnostico.json").write_text(json.dumps(filas, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
