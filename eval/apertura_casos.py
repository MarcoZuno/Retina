"""Mide la apertura arreglada en los 50 casos, con la regla sellada (docs/decisiones.md, 30-oct-2026).

A y B: la apertura de cada caso de punta a punta, igual que en la app. Primero SAM mira el borrador real y
luego corre el lazo. C es la trampa: 10 cuadros aprobados contra el objeto de otro caso, que el cuadro no tiene.
No usa retención. Se puede retomar: lo ya hecho no se vuelve a pagar, y el tope de gasto manda. Los casos,
títulos e imágenes se quedan fuera del repo; a la consola y al resumen solo salen conteos.

Uso (desde la raíz del repo):
    python eval/apertura_casos.py --casos CARPETA_CASOS_API --objetos OBJETOS.json --salida CARPETA
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina import apertura, meta_api, sam  # noqa: E402
from retina.arranque import wilson  # noqa: E402

CONDICION = {"A": 15, "B": 26, "C": 9}
CUADROS_TRAMPA = 10
COPIAR = ("manifiesto.json", "describir.json", "transcribir.json", "ligero.mp4")
# Objetos que pueden aparecer juntos: la trampa no pregunta por uno de la misma familia.
FAMILIAS = ({"food", "tortilla", "vegetable", "nopal", "coffee"}, {"dog", "cat", "cage"}, {"fair", "city", "dump", "castle"})


def leer(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def preparar(origen: Path, destino: Path, concepto: str | None) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    for nombre in COPIAR:
        if (origen / nombre).exists() and not (destino / nombre).exists():
            shutil.copyfile(origen / nombre, destino / nombre)
    if (origen / "cuadros").is_dir():
        shutil.copytree(origen / "cuadros", destino / "cuadros", dirs_exist_ok=True)
    previa = origen / "sam.json"
    if concepto and previa.exists() and leer(previa).get("concepto") == concepto and not (destino / "sam.json").exists():
        shutil.copyfile(previa, destino / "sam.json")


def una_apertura(origen: Path, destino: Path, concepto: str | None) -> dict:
    ruta = destino / "apertura.json"
    if ruta.exists():
        return leer(ruta)
    preparar(origen, destino, concepto)
    if concepto and not (destino / "sam.json").exists():
        sam.medir(destino, concepto)  # como en la app: SAM mira el borrador antes de reescribirlo
    s = apertura.armar(destino, leer(origen / "resultado.json")["video"]["titulo"], concepto)
    ruta.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    return s


def paso_promesa(s: dict) -> bool:
    return s["aprobada"] and any(c["id"] == "promesa" and c["paso"] for c in s["comprobaciones"])


def otra_familia(a: str, b: str) -> bool:
    return a != b and not any(a in f and b in f for f in FAMILIAS)


def trampa(salida: Path, cuadros: list[tuple[str, str]], objetos: list[str]) -> list[dict]:
    """Cada cuadro contra el siguiente objeto de la lista que no sea de su familia."""
    ruta = salida / "trampa.json"
    filas = leer(ruta)["filas"] if ruta.exists() else []
    for i, (codigo, objeto) in enumerate(cuadros[:CUADROS_TRAMPA]):
        if i < len(filas):
            continue
        ajeno = next(o for k in range(1, len(objetos) + 1) if otra_familia(objeto, o := objetos[(i + k) % len(objetos)]))
        r = sam.medir_imagen(salida / "casos" / codigo / "apertura-cuadro1-ilustracion-ia.png", ajeno)
        filas.append({"codigo": codigo, "objeto": objeto, "ajeno": ajeno, "rechazo": not r.get("aparece", True), "sam": r})
        ruta.write_text(json.dumps({"filas": filas}, ensure_ascii=False, indent=1), encoding="utf-8")
    return filas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--casos", type=Path, required=True)
    ap.add_argument("--objetos", type=Path, required=True, help="La lista privada que se fijó antes de medir.")
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    meta_api._cargar_env()
    codigos, objetos = leer(a.casos / "casos.json"), leer(a.objetos)
    inicio = meta_api.gastado_usd()
    hechas: dict[str, dict] = {}
    for i, c in enumerate(codigos, 1):
        try:
            hechas[c] = una_apertura(a.casos / "casos" / c, a.salida / "casos" / c, objetos.get(c))
        except meta_api.TopeAlcanzado as e:
            print(f"Me detengo: {e}")
            return
        except Exception as e:  # noqa: BLE001 — un caso fallido no tumba la medición; se retoma después
            print(f"{i}/{len(codigos)} falló: {type(e).__name__}", flush=True)
            continue
        print(f"{i}/{len(codigos)} aprobada={hechas[c]['aprobada']} correcciones={hechas[c]['vueltas']}", flush=True)
    if len(hechas) < len(codigos):
        print(f"Faltan {len(codigos) - len(hechas)} casos: corre otra vez para retomar. Sin resumen todavía.")
        return

    grupo_a = [c for c in codigos if objetos.get(c)]
    grupo_b = [c for c in codigos if not objetos.get(c)]
    pasan_a = [c for c in grupo_a if paso_promesa(hechas[c])]
    pasan_b = [c for c in grupo_b if hechas[c]["aprobada"]]
    cuadros = [(c, objetos[c]) for c in pasan_a]
    filas = trampa(a.salida, cuadros, [objetos[c] for c in grupo_a])
    rechaza = sum(f["rechazo"] for f in filas)
    sin_promesa = [c for c in grupo_a if not (hechas[c]["antes"]["promesa"] or {}).get("aparece")]
    resumen = {
        "regla": "docs/decisiones.md, 30-oct-2026",
        "A": {"n": len(grupo_a), "pasan": len(pasan_a), "ic95": wilson(len(pasan_a), len(grupo_a)), "pasa": len(pasan_a) >= CONDICION["A"]},
        "B": {"n": len(grupo_b), "pasan": len(pasan_b), "pasa": len(pasan_b) >= CONDICION["B"]},
        "C": {"n": len(filas), "rechaza": rechaza, "pasa": rechaza >= CONDICION["C"]},
        "correcciones_de_las_aprobadas": Counter(str(h["vueltas"]) for h in hechas.values() if h["aprobada"]),
        "que_fallo_en_las_no_aprobadas": Counter(p["id"] for h in hechas.values() if not h["aprobada"]
                                                 for p in h["intentos"][-1]["problemas"]),
        "que_se_corrigio": Counter(p["id"] for h in hechas.values() for x in h["intentos"][:-1] for p in x["problemas"]),
        "sin_comprobar_por_falla_de_sam": sum(bool(h["no_comprobe"]) for h in hechas.values()),
        "borrador_sin_promesa_en_3_s": len(sin_promesa),
        "de_esos_la_nueva_si": sum(c in pasan_a for c in sin_promesa),
        "usd": round(meta_api.gastado_usd() - inicio, 2),
    }
    resumen["pasa_todo"] = all(resumen[k]["pasa"] for k in "ABC")
    (a.salida / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False))


if __name__ == "__main__":
    main()
