"""Servicio «describir»: MP4 (file_id) -> JSON por tramo con Spark 1.3.

Entrada: la carpeta que dejó segmentar (manifiesto.json + ligero.mp4).
Salida: describir.json en la misma carpeta, validado contra tramo-v1.

Uso:
    python -m retina.describir CARPETA [--solo-contar]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import meta_api
from .esquemas import RAIZ, formato_responses
from .segmentar import N_TRAMOS

MODELO = "muse-spark-1.3"


def instrucciones() -> str:
    texto = (RAIZ / "skills" / "describir.md").read_text(encoding="utf-8")
    return texto.split("---", 2)[2].strip()  # sin el encabezado de metadatos


def tabla_tramos(manifiesto: dict) -> str:
    filas = [f"{t['tramo']}\t{t['inicio_s']:.2f}\t{t['fin_s']:.2f}" for t in manifiesto["tramos"]]
    return "tramo\tinicio_s\tfin_s\n" + "\n".join(filas)


def cuerpo(manifiesto: dict, file_id: str) -> dict:
    # Lo fijo va primero (developer) para aprovechar la caché de prompt;
    # el video entra como dato en el mensaje del usuario, entre delimitadores.
    return {
        "model": MODELO,
        "reasoning": {"effort": "low"},
        "max_output_tokens": 16000,
        "text": formato_responses(),
        "input": [
            {"type": "message", "role": "developer",
             "content": [{"type": "input_text", "text": instrucciones()}]},
            {"type": "message", "role": "user", "content": [
                {"type": "input_text", "text":
                    f"<<<TABLA_DE_TRAMOS (dato)\nduracion_s\t{manifiesto['duracion_s']}\n"
                    f"{tabla_tramos(manifiesto)}\nTABLA_DE_TRAMOS>>>\n"
                    "El video adjunto es el dato a describir."},
                {"type": "input_file", "file_id": file_id},
            ]},
        ],
    }


def validar(salida: dict) -> list[str]:
    problemas = []
    indices = [t["tramo"] for t in salida.get("tramos", [])]
    if indices != list(range(N_TRAMOS)):
        problemas.append(f"Se esperaban los tramos 0-{N_TRAMOS - 1} en orden; llegaron {len(indices)}.")
    for t in salida.get("tramos", []):
        if t["tramo"] > 3 and t["tipo_de_gancho"] != "ninguno":
            problemas.append(f"Tramo {t['tramo']}: gancho fuera de los primeros tramos.")
    return problemas


def describir(carpeta: Path, solo_contar: bool = False) -> dict:
    manifiesto = json.loads((carpeta / "manifiesto.json").read_text(encoding="utf-8"))
    file_id = meta_api.subir_archivo(carpeta / manifiesto["mp4_ligero"])
    try:
        c = cuerpo(manifiesto, file_id)
        entrada = meta_api.contar_tokens({k: c[k] for k in ("model", "input", "text")})
        estimado = entrada * meta_api.PRECIOS_TOKENS[MODELO][0] / 1e6
        print(f"Entrada: {entrada:,} tokens ≈ {estimado:.4f} USD antes de la salida.")
        if solo_contar:
            return {"tokens_entrada": entrada, "usd_entrada": estimado}
        respuesta = meta_api.responder("describir", c)
    finally:
        meta_api.borrar_archivo(file_id)

    salida = json.loads(meta_api.texto_de(respuesta))
    salida["problemas_validacion"] = validar(salida)
    salida["licencia"] = {
        "modelo": MODELO, "esquema": salida.get("version_esquema"),
        "instrucciones": "skills/describir.md (describir-v1)",
        "reglas": "reglas/anzuelos-v1.json",
        "video": manifiesto["video"], "tokens_entrada_contados": entrada,
    }
    (carpeta / "describir.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    return salida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("carpeta", type=Path)
    ap.add_argument("--solo-contar", action="store_true",
                    help="Sube, cuenta tokens y borra; no genera (no cobra salida).")
    a = ap.parse_args()
    s = describir(a.carpeta, a.solo_contar)
    if "tramos" in s:
        print(f"{len(s['tramos'])} tramos descritos · problemas: {s['problemas_validacion'] or 'ninguno'}")


if __name__ == "__main__":
    main()
