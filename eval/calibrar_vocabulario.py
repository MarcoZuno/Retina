"""Calibra el vocabulario de SAM 3.1: qué palabras de la lista cerrada encuentra de verdad en dibujos de Muse Image.

La medición del 30-oct falló porque SAM no reconoce palabras como «tortilla» o «nopal», aunque el objeto esté en el
dibujo. Aquí cada palabra se dibuja en dos escenas inventadas y SAM la busca. Si la encuentra en las dos, se busca tal
cual. Si no, se prueba su palabra general (PADRES), también en las dos. Si tampoco, o si Muse Image no la dibuja, esa
palabra no se puede comprobar con SAM y sale de la lista. Sin datos de nadie.

Escribe reglas/sam-vocabulario-v1.json. Se puede retomar: lo ya medido no se vuelve a pagar.

Uso (desde la raíz del repo):
    python eval/calibrar_vocabulario.py --salida CARPETA_DE_DIBUJOS [--aprobar]
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina import meta_api, sam, storyboard  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "reglas" / "sam-vocabulario-v1.json"
ESCENAS = ("Una escena sencilla sobre fondo liso.", "Una escena cotidiana en México.")
HILOS = 4
GENERALES = {
    "food": "bean bread cake candy corn dish egg fruit meat rice soup taco tortilla vegetable",
    "animal": "bear bee bird cat chicken cow dog fish horse insect kitten lion monkey mosquito pet pig puppy rabbit "
              "snake tiger turtle",
    "plant": "cactus flower nopal tree",
    "fabric": "handkerchief scarf",
    "building": "castle church home hospital house prison restaurant school shop shelter stadium store office",
    "bottle": "drink milk",
    "cup": "coffee",
    "trash": "dump garbage landfill",
    "phone": "smartphone",
    "screen": "computer laptop tv",
}
PADRES = {hijo: general for general, hijos in GENERALES.items() for hijo in hijos.split()}


def dibujar(carpeta: Path, palabra: str, n: int) -> Path | None:
    destino = carpeta / f"{palabra}-{n}.png"
    if destino.exists():
        return destino
    prompt = f"{storyboard.ESTILO.format(i=1)}{ESCENAS[n]} Main subject, large and centered: {palabra}."
    try:
        meta_api._revisar_tope(meta_api.PRECIO_IMAGEN[storyboard.MODELO])
        storyboard.dibujar_uno(prompt, destino, servicio="calibrar")
    except meta_api.TopeAlcanzado:
        raise
    except RuntimeError:
        return None  # Muse Image rechazó el pedido o falló: esa palabra no se puede comprobar
    return destino


def la_encuentra(imagenes: list[Path], palabra: str) -> bool:
    return all(sam.medir_imagen(i, palabra).get("aparece") for i in imagenes)


def calibrar(carpeta: Path, palabra: str) -> dict:
    imagenes = [dibujar(carpeta, palabra, n) for n in range(len(ESCENAS))]
    if not all(imagenes):
        return {"palabra": palabra, "buscar": None, "motivo": "Muse Image no la dibujó"}
    if la_encuentra(imagenes, palabra):
        return {"palabra": palabra, "buscar": palabra}
    padre = PADRES.get(palabra)
    if padre and la_encuentra(imagenes, padre):
        return {"palabra": palabra, "buscar": padre}
    return {"palabra": palabra, "buscar": None, "motivo": "SAM no la encontró"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--aprobar", action="store_true", help="Sin esto solo dice cuánto costaría.")
    a = ap.parse_args()
    palabras = sorted(sam._lista()[0])
    print(f"{len(palabras)} palabras · hasta USD {len(palabras) * 2 * 0.03:.2f}")
    if not a.aprobar:
        return
    meta_api._cargar_env()
    a.salida.mkdir(parents=True, exist_ok=True)
    avance = a.salida / "calibracion.jsonl"
    hechas = {}
    if avance.exists():
        for linea in avance.read_text(encoding="utf-8").splitlines():
            d = json.loads(linea)
            hechas[d["palabra"]] = d
    candado = threading.Lock()

    def una(palabra: str) -> None:
        d = calibrar(a.salida, palabra)
        with candado:
            hechas[palabra] = d
            with avance.open("a", encoding="utf-8") as f:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
            print(f"{len(hechas)}/{len(palabras)} {palabra} -> {d['buscar']}", flush=True)

    with ThreadPoolExecutor(max_workers=HILOS) as hilos:
        for futuro in [hilos.submit(una, p) for p in palabras if p not in hechas]:
            futuro.result()

    buscar = {p: hechas[p]["buscar"] for p in palabras if hechas[p]["buscar"]}
    DESTINO.write_text(json.dumps({
        "version": "sam-vocabulario-v1",
        "fecha": "2026-10-30",
        "uso": "Qué se le pide a SAM 3.1 por cada palabra de sam-permitidos-v1.json. La palabra de la izquierda es lo que se "
               "dibuja y la de la derecha lo que se busca. Sale de eval/calibrar_vocabulario.py: SAM tuvo que encontrarla en dos "
               "dibujos de Muse Image. Lo que no está aquí no se puede comprobar con SAM.",
        "buscar": buscar,
        "no_se_puede_comprobar": {p: hechas[p]["motivo"] for p in palabras if not hechas[p]["buscar"]},
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    directas = sum(p == t for p, t in buscar.items())
    print(f"{directas} tal cual · {len(buscar) - directas} con su palabra general · {len(palabras) - len(buscar)} fuera")


if __name__ == "__main__":
    main()
