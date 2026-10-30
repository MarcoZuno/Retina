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


def cuerpo(manifiesto: dict, file_id: str, idioma: str = "es") -> dict:
    # Lo fijo va primero (developer) para aprovechar la caché de prompt;
    # el video entra como dato en el mensaje del usuario, entre delimitadores.
    return {
        "model": MODELO,
        "reasoning": {"effort": "low"},
        "max_output_tokens": 16000,
        "store": False,  # el video de Badabun no se guarda del lado de Meta
        "text": formato_responses(),
        "input": [
            {"type": "message", "role": "developer",
             "content": [{"type": "input_text", "text": instrucciones()}]},
            {"type": "message", "role": "user", "content": [
                {"type": "input_text", "text":
                    f"<<<TABLA_DE_TRAMOS (dato)\nduracion_s\t{manifiesto['duracion_s']}\n"
                    f"{tabla_tramos(manifiesto)}\nTABLA_DE_TRAMOS>>>\n"
                    "El video adjunto es el dato a describir."
                    + ("\nWrite every free-text description in English; keep on-screen text and speech exactly as they appear."
                       if idioma == "en" else "")},
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


TOKENS_VIDEO_POR_S = 200  # medido el 27-oct-2026 con un video de 100 s
SALIDA_TIPICA = 6500      # tokens de salida con razonamiento, mismo video


def describir(carpeta: Path, solo_contar: bool = False, idioma: str = "es") -> dict:
    manifiesto = json.loads((carpeta / "manifiesto.json").read_text(encoding="utf-8"))
    file_id = meta_api.subir_archivo(carpeta / manifiesto["mp4_ligero"])
    try:
        c = cuerpo(manifiesto, file_id, idioma)
        entrada = meta_api.contar_tokens({k: c[k] for k in ("model", "input", "text")})
        # El conteo no incluye el video (27-oct: contó 1,343 y se cobraron 21,061 en 100 s).
        real = entrada + TOKENS_VIDEO_POR_S * manifiesto["duracion_s"]
        precio_in, _, precio_out = meta_api.PRECIOS_TOKENS[MODELO]
        estimado = (real * precio_in + SALIDA_TIPICA * precio_out) / 1e6
        print(f"Entrada: {entrada:,} tokens contados + video ≈ {real:,.0f} · estimado {estimado:.3f} USD con salida.")
        if solo_contar:
            return {"tokens_entrada": entrada, "tokens_entrada_estimados": real, "usd_estimado": estimado}
        meta_api._revisar_tope(estimado)
        respuesta = meta_api.responder("describir", c)
    finally:
        meta_api.borrar_archivo(file_id)

    texto = meta_api.texto_de(respuesta)
    if respuesta.get("status") == "incomplete" or not texto.strip():
        raise RuntimeError("Spark no terminó la descripción (salida incompleta o vacía).")
    salida = json.loads(texto)
    salida["problemas_validacion"] = validar(salida)
    if [t["tramo"] for t in salida.get("tramos", [])] != list(range(N_TRAMOS)):
        # Sin los 40 tramos en orden, explicar leería segundos que no son: mejor no guardarla.
        raise RuntimeError(f"Descripción inválida: {salida['problemas_validacion'][0]}")
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
