"""Retina como agente sobre los casos que ya corrió eval/casos_api.py.

Para cada caso con resultado.json, corre el agente (herramientas + validador
en el ciclo) y anota turnos, herramientas, si cayó al respaldo y el costo.
Así se compara contra «explicar» de una sola vuelta sobre los mismos videos.

Uso (desde la raíz del repo):
    python eval/casos_agente.py --casos CARPETA --voz VOZ.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina import meta_api  # noqa: E402
from retina.agente import cargar_voz, correr_agente  # noqa: E402
from retina.predecir import Modelo  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--casos", type=Path, required=True, help="La --salida de eval/casos_api.py.")
    ap.add_argument("--voz", type=Path, required=True)
    a = ap.parse_args()
    modelo = Modelo.cargar(a.casos / "modelos" / "predecir-hasta-corte.pkl")
    voz = cargar_voz(a.voz)
    tabla = a.casos / "tabla-agente.jsonl"
    hechos = {json.loads(l)["codigo"] for l in tabla.open(encoding="utf-8")} if tabla.exists() else set()
    codigos = [c for c in json.loads((a.casos / "casos.json").read_text(encoding="utf-8"))
               if (a.casos / "casos" / c / "resultado.json").exists() and c not in hechos]
    for i, c in enumerate(codigos, 1):
        t0, gasto0 = time.time(), meta_api.gastado_usd()
        try:
            t = correr_agente(a.casos / "casos" / c, modelo, voz)
        except meta_api.TopeAlcanzado as e:
            print(f"Me detengo: {e}")
            break
        lic = t["licencia"]
        herramientas = [x["herramienta"] for x in lic["traza"] if "herramienta" in x]
        fila = {"codigo": c, "fuente": lic["fuente"], "turnos": lic["turnos"], "herramientas": herramientas,
                "entregas": herramientas.count("entregar_tarjeta"), "uso_sam": "medir_lo_prometido" in herramientas,
                "uso_parecidos": "buscar_parecidos" in herramientas, "con_sugerencia": bool(t["que_cambiar"]),
                "confianza": t["confianza"], "usd": round(meta_api.gastado_usd() - gasto0, 4),
                "segundos": round(time.time() - t0, 1)}
        with tabla.open("a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
        print(f"{i}/{len(codigos)} {c} · {fila['fuente']} · {fila['turnos']} turnos · USD {fila['usd']:.3f}", flush=True)
    print(f"Gastado en total: USD {meta_api.gastado_usd():.2f} de {meta_api.tope_usd():.0f}")


if __name__ == "__main__":
    main()
