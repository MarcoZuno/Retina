"""Tercera medición de la apertura: apertura-v2 en videos nuevos, con un grupo sin promesa visible y trampas cercanas.

La regla está sellada en docs/decisiones.md. Como la segunda (eval/apertura_nuevos.py), usa el título y lo que se dice, sin
retención y sin el video; lo demás es el mismo lazo de la app. Lo que cambia frente a la segunda:
- el código ya no le ordena a Muse Image dibujar lo que SAM va a buscar: el dibujo sale solo de lo que Spark escribió;
- 30 videos con promesa visible y 20 sin ella;
- la trampa lejana usa palabras que SAM encuentra tal cual; además se reporta una trampa cercana (otro objeto de la misma
  familia), donde el revisor es más débil.

--elegir fija los casos antes de medir. --piloto elige otros 6 para afinar: esos no entran a la medición. Se puede retomar:
lo ya hecho no se vuelve a pagar. Los casos, títulos e imágenes se quedan fuera del repo; a la consola solo salen conteos.

Uso (desde la raíz del repo):
    python eval/apertura_v2.py --base BASE.csv --voz VOZ.jsonl --excluir A.json B.json --salida CARPETA --elegir [--piloto]
    python eval/apertura_v2.py --base BASE.csv --voz VOZ.jsonl --salida CARPETA
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from apertura_nuevos import datos_sin_video, leer, voces  # noqa: E402
from retina import apertura, meta_api, sam  # noqa: E402
from retina.arranque import wilson  # noqa: E402
from retina.curvas import CORTE_PRUEBA, FIN_PRUEBA, cargar  # noqa: E402

SEMILLA, SEMILLA_PILOTO, MAX_DURACION_S = 20261031, 20261032, 240
N_CON, N_SIN, PILOTO_CON, PILOTO_SIN = 30, 20, 4, 2
CONDICION_CON, CONDICION_SIN, CONDICION_TRAMPA, CUADROS_TRAMPA = 24, 16, 9, 10
FAMILIAS = (("dog", "cat", "rabbit", "pig", "cow", "horse", "monkey", "bear", "animal"), ("puppy", "kitten"), ("lion", "tiger"),
            ("bird", "chicken"), ("fish", "turtle", "snake"), ("mosquito", "bee", "insect"), ("bread", "cake", "taco", "meat", "egg", "corn", "fruit", "soup", "food"),
            ("coffee", "drink", "water"), ("house", "home", "church", "castle", "shop", "store", "stadium", "building"),
            ("car", "truck", "bus", "ambulance", "train"), ("motorcycle", "bicycle"), ("plane", "boat"), ("cup", "bottle", "glass", "pot", "plate", "dish"),
            ("book", "paper"), ("box", "bag"), ("chair", "table", "bed"), ("computer", "laptop", "smartphone", "tv", "screen"), ("tree", "flower", "plant", "cactus"),
            ("pill", "medicine"), ("road", "street", "bridge"), ("sun", "moon"))


def elegir(filas: list[dict], voz: dict, fuera: set, destino: Path, semilla: int, n_con: int, n_sin: int) -> None:
    baraja = sorted((v for v in filas if v["codigo"] in voz and v["codigo"] not in fuera and v["dur"] <= MAX_DURACION_S
                     and CORTE_PRUEBA <= v["fecha"] < FIN_PRUEBA), key=lambda v: v["codigo"])
    random.Random(semilla).shuffle(baraja)
    con, sin, revisados = {}, [], 0
    for v in baraja:
        if len(con) == n_con and len(sin) == n_sin:
            break
        revisados += 1
        objeto = sam.objeto_del_titulo(v.get("titulo") or v["archivo"])
        if objeto and len(con) < n_con:
            con[v["codigo"]] = objeto
        elif not objeto and len(sin) < n_sin:
            sin.append(v["codigo"])
    destino.write_text(json.dumps({"semilla": semilla, "revisados": revisados, "con_promesa": con, "sin_promesa": sin},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(con)} con promesa y {len(sin)} sin ella, de {revisados} títulos revisados")


def un_caso(v: dict, tramos: list, objeto: str | None, carpeta: Path) -> dict:
    ruta = carpeta / "apertura.json"
    if ruta.exists():
        return leer(ruta)
    carpeta.mkdir(parents=True, exist_ok=True)
    s = apertura.lazo(datos_sin_video(v.get("titulo") or v["archivo"], tramos, v["dur"]), objeto, apertura.pedir,
                      lambda i, c: apertura.dibujar_cuadro(carpeta, i, c),
                      lambda imagen, c: sam.medir_imagen(imagen, sam.termino(c) or c))
    ruta.write_text(json.dumps({**s, "version": apertura.VERSION, "objeto": objeto}, ensure_ascii=False, indent=1), encoding="utf-8")
    return s


def paso_con_promesa(s: dict) -> bool:
    return s["aprobada"] and any(c["id"] == "promesa" and c["paso"] for c in s["comprobaciones"])


def familia(objeto: str) -> tuple | None:
    return next((f for f in FAMILIAS if objeto in f), None)


def lejano(objeto: str, objetos: list[str], i: int) -> str | None:
    """El siguiente objeto de la lista que SAM encuentra tal cual y que no es de la familia de este."""
    propia = familia(objeto) or (objeto,)
    tal_cual = [o for o in objetos if sam.termino(o) == o and o not in propia]
    return tal_cual[i % len(tal_cual)] if tal_cual else None


def cercano(objeto: str) -> str | None:
    """Otro objeto de la misma familia, que el cuadro no pidió."""
    f = familia(objeto)
    return None if not f or len(f) < 2 else f[(f.index(objeto) + 1) % len(f)]


def trampa_pasa(filas: list[dict]) -> bool:
    return len(filas) == CUADROS_TRAMPA and sum(f["rechazo"] for f in filas) >= CONDICION_TRAMPA


def trampa(salida: Path, nombre: str, cuadros: list[tuple[str, str]], ajeno_de) -> list[dict]:
    ruta = salida / nombre
    filas = leer(ruta)["filas"] if ruta.exists() else []
    hechos = {f["codigo"] for f in filas}
    for i, (codigo, objeto) in enumerate(cuadros):
        ajeno = ajeno_de(sam.termino(objeto) or objeto, i)
        if len(filas) == CUADROS_TRAMPA:
            break
        if not ajeno or codigo in hechos:
            continue
        r = sam.medir_imagen(salida / "casos" / codigo / "apertura-cuadro1-ilustracion-ia.png", ajeno)
        filas.append({"codigo": codigo, "objeto": objeto, "ajeno": ajeno, "rechazo": not r.get("aparece", True), "pct": r.get("pct_maximo_del_cuadro")})
        ruta.write_text(json.dumps({"filas": filas}, ensure_ascii=False, indent=1), encoding="utf-8")
    return filas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--voz", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--excluir", type=Path, nargs="*", default=[], help="Listas privadas de códigos ya usados.")
    ap.add_argument("--elegir", action="store_true", help="Fija los casos; no mide nada.")
    ap.add_argument("--piloto", action="store_true", help="Con --elegir: seis casos para afinar, fuera de la medición.")
    a = ap.parse_args()
    meta_api._cargar_env()
    a.salida.mkdir(parents=True, exist_ok=True)
    filas, voz, lista = cargar(a.base), voces(a.voz), a.salida / "elegidos.json"
    if a.elegir:
        fuera = set()
        for ruta in a.excluir:
            d = leer(ruta)
            fuera |= set(d.get("elegidos", d) if isinstance(d, dict) else d)
            fuera |= set(d.get("con_promesa", [])) | set(d.get("sin_promesa", [])) if isinstance(d, dict) else set()
        semilla, n_con, n_sin = (SEMILLA_PILOTO, PILOTO_CON, PILOTO_SIN) if a.piloto else (SEMILLA, N_CON, N_SIN)
        elegir(filas, voz, fuera, lista, semilla, n_con, n_sin)
        return
    elegidos, por_codigo, inicio = leer(lista), {v["codigo"]: v for v in filas}, meta_api.gastado_usd()
    con, sin = elegidos["con_promesa"], elegidos["sin_promesa"]
    casos = [*con.items(), *((c, None) for c in sin)]
    hechas = {}
    for i, (c, objeto) in enumerate(casos, 1):
        try:
            hechas[c] = un_caso(por_codigo[c], voz[c], objeto, a.salida / "casos" / c)
        except meta_api.TopeAlcanzado as e:
            print(f"Me detengo: {e}")
            return
        except Exception as e:  # noqa: BLE001 — un caso fallido no tumba la medición; se retoma después
            print(f"{i}/{len(casos)} falló: {type(e).__name__}", flush=True)
            continue
        print(f"{i}/{len(casos)} aprobada={hechas[c]['aprobada']} correcciones={hechas[c]['vueltas']}", flush=True)
    if len(hechas) < len(casos):
        print("Faltan casos: corre otra vez para retomar. Sin resumen todavía.")
        return
    pasan_con = [c for c in con if paso_con_promesa(hechas[c])]
    pasan_sin = [c for c in sin if hechas[c]["aprobada"]]
    cuadros = [(c, con[c]) for c in pasan_con]
    objetos = [sam.termino(o) or o for o in con.values()]
    filas_lejos = trampa(a.salida, "trampa-lejana.json", cuadros, lambda o, i: lejano(o, objetos, i))
    filas_cerca = trampa(a.salida, "trampa-cercana.json", cuadros, lambda o, i: cercano(o))
    resumen = {
        "regla": "docs/decisiones.md, tercera medición",
        "con_promesa": {"n": len(con), "pasan": len(pasan_con), "ic95": wilson(len(pasan_con), len(con)), "pasa": len(pasan_con) >= CONDICION_CON},
        "sin_promesa": {"n": len(sin), "pasan": len(pasan_sin), "ic95": wilson(len(pasan_sin), len(sin)), "pasa": len(pasan_sin) >= CONDICION_SIN},
        "trampa_lejana": {"n": len(filas_lejos), "rechaza": sum(f["rechazo"] for f in filas_lejos), "pasa": trampa_pasa(filas_lejos)},
        "trampa_cercana": {"n": len(filas_cerca), "rechaza": sum(f["rechazo"] for f in filas_cerca)},
        "titulos_revisados": elegidos["revisados"],
        "correcciones_de_las_aprobadas": Counter(str(h["vueltas"]) for h in hechas.values() if h["aprobada"]),
        "que_fallo_en_las_no_aprobadas": Counter(p["id"] for h in hechas.values() if not h["aprobada"] for p in h["intentos"][-1]["problemas"]),
        "que_se_corrigio": Counter(p["id"] for h in hechas.values() for x in h["intentos"][:-1] for p in x["problemas"]),
        "sin_comprobar_por_falla_de_sam": sum(bool(h["no_comprobe"]) for h in hechas.values()),
        "usd": round(meta_api.gastado_usd() - inicio, 2),
    }
    resumen["pasa_todo"] = all(resumen[k]["pasa"] for k in ("con_promesa", "sin_promesa", "trampa_lejana"))
    (a.salida / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False))


if __name__ == "__main__":
    main()
