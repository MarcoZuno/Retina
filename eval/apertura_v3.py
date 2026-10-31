"""Cuarta medición de la apertura: apertura-v3 en videos nuevos, con los tres dibujos revisados.

La regla está sellada en docs/decisiones.md. Es la misma forma de la tercera (eval/apertura_v2.py): título y lo que se dice, sin
retención y sin el video. Cambia que Muse Spark 1.3 mira los cuadros que SAM no revisó, que una lista ya no pasa y que Spark Open
puede decir que el inicio ya funciona, si el código lo confirma. Eso se cuenta aparte.

--elegir fija los casos antes de medir. --piloto elige otros 6 para afinar: esos no entran a la medición. Se puede retomar: lo ya
hecho no se vuelve a pagar. Los casos, títulos e imágenes se quedan fuera del repo; a la consola solo salen conteos.

Uso (desde la raíz del repo):
    python eval/apertura_v3.py --base BASE.csv --voz VOZ.jsonl --excluir A.json --salida CARPETA --elegir [--piloto]
    python eval/apertura_v3.py --base BASE.csv --voz VOZ.jsonl --salida CARPETA
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from apertura_nuevos import datos_sin_video, leer, voces  # noqa: E402
from apertura_v2 import CONDICION_CON, CONDICION_SIN, N_CON, N_SIN, PILOTO_CON, PILOTO_SIN, cercano, elegir, lejano, trampa, trampa_pasa  # noqa: E402
from retina import apertura, meta_api, sam  # noqa: E402
from retina.arranque import wilson  # noqa: E402
from retina.curvas import cargar  # noqa: E402

SEMILLA, SEMILLA_PILOTO, MAX_YA_FUNCIONA = 20261101, 20261102, 10


def un_caso(v: dict, tramos: list, objeto: str | None, carpeta: Path) -> dict:
    ruta = carpeta / "apertura.json"
    if ruta.exists():
        return leer(ruta)
    carpeta.mkdir(parents=True, exist_ok=True)
    s = apertura.lazo(datos_sin_video(v.get("titulo") or v["archivo"], tramos, v["dur"]), objeto, apertura.pedir,
                      lambda i, c: apertura.dibujar_cuadro(carpeta, i, c),
                      lambda imagen, c: sam.medir_imagen(imagen, sam.termino(c) or c), comprobar=apertura.comprobar_cuadro)
    ruta.write_text(json.dumps({**s, "version": apertura.VERSION, "objeto": objeto}, ensure_ascii=False, indent=1), encoding="utf-8")
    return s


def paso(s: dict, con_promesa: bool) -> bool:
    if not s["aprobada"]:
        return False
    return bool(s.get("ya_funciona")) or not con_promesa or any(c["id"] == "promesa" and c["paso"] for c in s["comprobaciones"])


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
            fuera |= set(d) if isinstance(d, list) else set(d.get("con_promesa", [])) | set(d.get("sin_promesa", []))
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
        print(f"{i}/{len(casos)} aprobada={hechas[c]['aprobada']} correcciones={hechas[c]['vueltas']} ya_funciona={bool(hechas[c].get('ya_funciona'))}", flush=True)
    if len(hechas) < len(casos):
        print("Faltan casos: corre otra vez para retomar. Sin resumen todavía.")
        return
    pasan_con = [c for c in con if paso(hechas[c], True)]
    pasan_sin = [c for c in sin if paso(hechas[c], False)]
    ya = sum(bool(h.get("ya_funciona")) for h in hechas.values())
    cuadros = [(c, con[c]) for c in pasan_con if not hechas[c].get("ya_funciona")]
    objetos = [sam.termino(o) or o for o in con.values()]
    lejos = trampa(a.salida, "trampa-lejana.json", cuadros, lambda o, i: lejano(o, objetos, i))
    cerca = trampa(a.salida, "trampa-cercana.json", cuadros, lambda o, i: cercano(o))
    revisados = [f["coincide"] for h in hechas.values() if h.get("despues") for f in h["despues"].get("cuadros_revisados", [])]
    resumen = {
        "regla": "docs/decisiones.md, cuarta medición",
        "con_promesa": {"n": len(con), "pasan": len(pasan_con), "ic95": wilson(len(pasan_con), len(con)), "pasa": len(pasan_con) >= CONDICION_CON},
        "sin_promesa": {"n": len(sin), "pasan": len(pasan_sin), "ic95": wilson(len(pasan_sin), len(sin)), "pasa": len(pasan_sin) >= CONDICION_SIN},
        "trampa_lejana": {"n": len(lejos), "rechaza": sum(f["rechazo"] for f in lejos), "pasa": trampa_pasa(lejos)},
        "trampa_cercana": {"n": len(cerca), "rechaza": sum(f["rechazo"] for f in cerca)},
        "ya_funciona": {"n": ya, "pasa": ya <= MAX_YA_FUNCIONA},
        "cuadros_revisados": {"coinciden": revisados.count(True), "sin_revisar": revisados.count(None), "no_coinciden": revisados.count(False)},
        "titulos_revisados": elegidos["revisados"],
        "correcciones_de_las_aprobadas": Counter(str(h["vueltas"]) for h in hechas.values() if h["aprobada"]),
        "que_fallo_en_las_no_aprobadas": Counter(p["id"] for h in hechas.values() if not h["aprobada"] for p in h["intentos"][-1]["problemas"]),
        "que_se_corrigio": Counter(p["id"] for h in hechas.values() for x in h["intentos"][:-1] for p in x["problemas"]),
        "sin_comprobar_por_falla_de_sam": sum(bool(h["no_comprobe"]) for h in hechas.values()),
        "usd": round(meta_api.gastado_usd() - inicio, 2),
    }
    resumen["pasa_todo"] = all(resumen[k]["pasa"] for k in ("con_promesa", "sin_promesa", "trampa_lejana", "ya_funciona"))
    (a.salida / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False))


if __name__ == "__main__":
    main()
