"""Segunda medición de la apertura: 30 videos que la primera no tocó, con el vocabulario calibrado de SAM.

La regla está sellada en docs/decisiones.md. No usa retención ni el video: solo el título y lo que se dice, porque lo
que falló la primera vez fue el dibujo y SAM, no la lectura del video. Por eso aquí no hay descripción de lo que se ve
ni revisión del borrador con SAM. Lo demás es el mismo lazo de la app: mismas instrucciones, reglas, dibujo y SAM.

--elegir fija los casos antes de medir: baraja con semilla los videos del periodo y se queda con los primeros 30 cuyo
título promete algo que SAM puede comprobar. Se puede retomar: lo ya hecho no se vuelve a pagar. Los casos, títulos e
imágenes se quedan fuera del repo; a la consola y al resumen solo salen conteos.

Uso (desde la raíz del repo):
    python eval/apertura_nuevos.py --base BASE.csv --voz VOZ.jsonl --casos CASOS.json --excluir EXCLUIR.json \
        --salida CARPETA --elegir
    python eval/apertura_nuevos.py --base BASE.csv --voz VOZ.jsonl --salida CARPETA
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina import apertura, integridad, meta_api, sam, transcribir  # noqa: E402
from retina.arranque import wilson  # noqa: E402
from retina.curvas import CORTE_PRUEBA, FIN_PRUEBA, cargar  # noqa: E402

SEMILLA, N_CASOS, MAX_DURACION_S = 20261030, 30, 240
CONDICION_CASOS, CONDICION_TRAMPA, CUADROS_TRAMPA = 24, 9, 10
FAMILIAS = ({"food", "tortilla", "vegetable", "nopal", "coffee", "cup", "plant", "cactus"},
            {"dog", "cat", "cage", "animal", "pet", "puppy", "kitten"}, {"fair", "city", "dump", "castle", "building", "house", "street"})


def leer(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def voces(ruta: Path) -> dict:
    return {d["codigo"]: d["tramos"] for d in map(json.loads, ruta.open(encoding="utf-8"))}


def elegir(filas: list[dict], voz: dict, fuera: set, destino: Path) -> None:
    baraja = sorted((v for v in filas if v["codigo"] in voz and v["codigo"] not in fuera and v["dur"] <= MAX_DURACION_S
                     and CORTE_PRUEBA <= v["fecha"] < FIN_PRUEBA), key=lambda v: v["codigo"])
    random.Random(SEMILLA).shuffle(baraja)
    elegidos, revisados = {}, 0
    for v in baraja:
        if len(elegidos) == N_CASOS:
            break
        revisados += 1
        if objeto := sam.objeto_del_titulo(v.get("titulo") or v["archivo"]):
            elegidos[v["codigo"]] = objeto
    destino.write_text(json.dumps({"revisados": revisados, "elegidos": elegidos}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(elegidos)} casos de {revisados} títulos revisados")


def datos_sin_video(titulo: str, tramos: list, dur: float) -> dict:
    voz = [(float(i), x) for i, x in tramos if x]
    dicho = " ".join(x for _, x in voz)
    lengua = transcribir.idioma_de(" ".join([titulo, *dicho.split()[:60]])) or "es"
    return {"duracion_video_s": dur, "titulo": titulo,
            "frases": [{"segundo": round(i, 1), "dice": x} for i, x in voz if i < dur / 4],
            "resto_de_lo_que_se_dice": " ".join(" ".join(x for i, x in voz if i >= dur / 4).split()[:apertura.MAX_PALABRAS_RESTO]),
            "idioma_de_la_apertura": apertura.IDIOMAS[lengua], "fuente": integridad.normalizar(f"{titulo} {dicho}"),
            "tema_obligatorio": transcribir.idioma_de(titulo) in (None, lengua)}


def un_caso(v: dict, tramos: list, objeto: str, carpeta: Path) -> dict:
    ruta = carpeta / "apertura.json"
    if ruta.exists():
        return leer(ruta)
    carpeta.mkdir(parents=True, exist_ok=True)
    s = apertura.lazo(datos_sin_video(v.get("titulo") or v["archivo"], tramos, v["dur"]), objeto, apertura.pedir,
                      lambda i, c, o: apertura.dibujar_cuadro(carpeta, i, c, o),
                      lambda imagen, c: sam.medir_imagen(imagen, sam.termino(c) or c))
    ruta.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    return s


def paso(s: dict) -> bool:
    return s["aprobada"] and any(c["id"] == "promesa" and c["paso"] for c in s["comprobaciones"])


def trampa_pasa(filas: list[dict]) -> bool:
    return len(filas) == CUADROS_TRAMPA and sum(f["rechazo"] for f in filas) >= CONDICION_TRAMPA


def otra_familia(a: str, b: str) -> bool:
    return a != b and not any(a in f and b in f for f in FAMILIAS)


def trampa(salida: Path, cuadros: list[tuple[str, str]], objetos: list[str]) -> list[dict]:
    """Cada cuadro aprobado contra el siguiente objeto de la lista que no sea de su familia."""
    ruta = salida / "trampa.json"
    filas = leer(ruta)["filas"] if ruta.exists() else []
    for i, (codigo, objeto) in enumerate(cuadros[:CUADROS_TRAMPA]):
        if i < len(filas):
            continue
        ajeno = next(o for k in range(1, len(objetos) + 1) if otra_familia(sam.termino(objeto), o := sam.termino(objetos[(i + k) % len(objetos)])))
        r = sam.medir_imagen(salida / "casos" / codigo / "apertura-cuadro1-ilustracion-ia.png", ajeno)
        filas.append({"objeto": objeto, "ajeno": ajeno, "rechazo": not r.get("aparece", True), "pct": r.get("pct_maximo_del_cuadro")})
        ruta.write_text(json.dumps({"filas": filas}, ensure_ascii=False, indent=1), encoding="utf-8")
    return filas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--voz", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--casos", type=Path, help="La lista de los 50 de la primera medición (no se pueden repetir).")
    ap.add_argument("--excluir", type=Path, help="Lista privada de códigos usados para afinar.")
    ap.add_argument("--elegir", action="store_true", help="Fija los casos; no mide nada.")
    a = ap.parse_args()
    meta_api._cargar_env()
    a.salida.mkdir(parents=True, exist_ok=True)
    filas, voz, lista = cargar(a.base), voces(a.voz), a.salida / "elegidos.json"
    if a.elegir:
        elegir(filas, voz, set(leer(a.casos)) | set(leer(a.excluir)), lista)
        return
    elegidos, por_codigo, inicio = leer(lista)["elegidos"], {v["codigo"]: v for v in filas}, meta_api.gastado_usd()
    hechas = {}
    for i, (c, objeto) in enumerate(elegidos.items(), 1):
        try:
            hechas[c] = un_caso(por_codigo[c], voz[c], objeto, a.salida / "casos" / c)
        except meta_api.TopeAlcanzado as e:
            print(f"Me detengo: {e}")
            return
        except Exception as e:  # noqa: BLE001 — un caso fallido no tumba la medición; se retoma después
            print(f"{i}/{len(elegidos)} falló: {type(e).__name__}", flush=True)
            continue
        print(f"{i}/{len(elegidos)} aprobada={hechas[c]['aprobada']} correcciones={hechas[c]['vueltas']}", flush=True)
    if len(hechas) < len(elegidos):
        print("Faltan casos: corre otra vez para retomar. Sin resumen todavía.")
        return
    pasan = [c for c in elegidos if paso(hechas[c])]
    filas_trampa = trampa(a.salida, [(c, elegidos[c]) for c in pasan], list(elegidos.values()))
    resumen = {
        "regla": "docs/decisiones.md, 30-oct-2026, segunda medición",
        "casos": {"n": len(elegidos), "pasan": len(pasan), "ic95": wilson(len(pasan), len(elegidos)), "pasa": len(pasan) >= CONDICION_CASOS},
        "trampa": {"n": len(filas_trampa), "rechaza": sum(f["rechazo"] for f in filas_trampa), "pasa": trampa_pasa(filas_trampa)},
        "titulos_revisados": leer(lista)["revisados"],
        "correcciones_de_las_aprobadas": Counter(str(h["vueltas"]) for h in hechas.values() if h["aprobada"]),
        "que_fallo_en_las_no_aprobadas": Counter(p["id"] for h in hechas.values() if not h["aprobada"] for p in h["intentos"][-1]["problemas"]),
        "que_se_corrigio": Counter(p["id"] for h in hechas.values() for x in h["intentos"][:-1] for p in x["problemas"]),
        "sin_comprobar_por_falla_de_sam": sum(bool(h["no_comprobe"]) for h in hechas.values()),
        "usd": round(meta_api.gastado_usd() - inicio, 2),
    }
    resumen["pasa_todo"] = resumen["casos"]["pasa"] and resumen["trampa"]["pasa"]
    (a.salida / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False))


if __name__ == "__main__":
    main()
