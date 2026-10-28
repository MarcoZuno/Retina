"""Spark Open (pesos abiertos, Baseten) contra Spark 1.3 (API de Meta) escribiendo la tarjeta.

Mismos 50 casos, mismas instrucciones (skills/explicar.md), mismos datos y el mismo validador.
Compara: cuántas tarjetas pasan el validador a la primera, cuántas se quedan sin sugerencia
cuando el nivel no es «bajo», cuántas traen pasos, y el costo. Cada motor escribe su archivo
(explicar-abierto.json / explicar-api.json), así que se puede retomar.

Uso (desde la raíz del repo):
    python eval/casos_spark_open.py --casos CARPETA_CASOS_API --motor abierto|api|abierto+api [--solo 5]

«abierto+api»: Spark Open escribe y Spark 1.3 solo rescata la tarjeta que el validador rechazó.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retina import meta_api  # noqa: E402
from retina import explicar as explicar_mod  # noqa: E402
from retina.explicar import explicar  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--casos", type=Path, required=True)
    ap.add_argument("--motor", choices=list(explicar_mod.MOTORES), required=True)
    ap.add_argument("--solo", type=int, default=0)
    a = ap.parse_args()
    sufijo = a.motor.replace("+", "-y-")
    nombre = f"explicar-{sufijo}.json"
    codigos = json.loads((a.casos / "casos.json").read_text(encoding="utf-8"))
    if a.solo:
        codigos = codigos[:a.solo]
    filas = []
    for i, c in enumerate(codigos, 1):
        carpeta = a.casos / "casos" / c
        arranque = json.loads((carpeta / "resultado.json").read_text(encoding="utf-8"))["arranque"]
        try:
            if not (carpeta / nombre).exists():
                explicar(carpeta, arranque, a.motor, nombre)
        except meta_api.TopeAlcanzado as e:
            print(f"Me detengo: {e}"); break
        except Exception as e:  # noqa: BLE001 - un caso fallido no tumba la comparación
            print(f"{i}/{len(codigos)} {c} · falló: {type(e).__name__}: {e}"); filas.append({"codigo": c, "fallo": True}); continue
        t = json.loads((carpeta / nombre).read_text(encoding="utf-8"))
        intentos = t["licencia"]["intentos"]
        filas.append({"codigo": c, "nivel": arranque["nivel"], "a_la_primera": not intentos[0]["problemas"],
                      "intentos": len(intentos), "con_cambio": bool(t["que_cambiar"]), "pasos": len(t.get("pasos", [])),
                      "escribio": t["licencia"]["modelo"]})
        print(f"{i}/{len(codigos)} {c} · {filas[-1]}", flush=True)
    ok = [f for f in filas if not f.get("fallo")]
    resumen = {"motor": a.motor, "casos": len(filas), "fallaron": len(filas) - len(ok),
               "pasan_a_la_primera": sum(f["a_la_primera"] for f in ok),
               "sin_cambio_con_nivel_no_bajo": sum(1 for f in ok if not f["con_cambio"] and f["nivel"] != "bajo"),
               "con_pasos": sum(1 for f in ok if f["pasos"]),
               "escritas_por_spark_open": sum(1 for f in ok if "open" in f["escribio"])}
    (a.casos / f"comparacion-{sufijo}.json").write_text(json.dumps({"resumen": resumen, "filas": filas},
                                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False))


if __name__ == "__main__":
    main()
