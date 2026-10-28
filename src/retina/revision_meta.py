"""Revisión del inicio según las recomendaciones públicas de Meta, por ventanas (0-3 s, 0-10 s).

Idea del equipo (28-oct): en vez de mirar solo el primer cuarto completo, revisar desde los
primeros segundos lo que Meta pide (gancho, mensaje pronto, que se entienda sin sonido,
contenido propio, vertical). Se calcula en código con lo que ya dejaron describir, transcribir
y SAM: no llama a ninguna API. Son buenas prácticas, no una predicción.

Uso:
    python -m retina.revision_meta CARPETA_DEL_CASO
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from .esquemas import RAIZ

REGLAS = RAIZ / "reglas" / "recomendaciones-meta-v1.json"
GANCHOS = {"pregunta": "una pregunta", "dato_impactante": "un dato fuerte", "promesa": "una promesa",
           "conflicto": "un conflicto", "imagen_impactante": "una imagen que llama la atención", "otro": "un gancho"}


def _leer(carpeta: Path, nombre: str) -> dict | None:
    p = carpeta / nombre
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _tramos_hasta(man: dict, desc: dict, s: float) -> list[dict]:
    lim = {t["tramo"]: (t["inicio_s"], t["fin_s"]) for t in man["tramos"]}
    return [{**d, "inicio_s": lim[d["tramo"]][0], "fin_s": lim[d["tramo"]][1]}
            for d in desc["tramos"] if lim[d["tramo"]][0] < s]


def _proporcion(video: Path) -> float | None:
    from .segmentar import _ffmpeg
    try:
        p = subprocess.run([_ffmpeg(), "-hide_banner", "-i", str(video)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    except (OSError, RuntimeError):
        return None
    m = re.search(r"Video:.*?\b(\d{2,5})x(\d{2,5})\b", p.stderr)
    return int(m.group(1)) / int(m.group(2)) if m else None


def revisar(carpeta: Path) -> list[dict]:
    reglas = {r["id"]: r for r in json.loads(REGLAS.read_text(encoding="utf-8"))["reglas"]}
    man, desc = _leer(carpeta, "manifiesto.json"), _leer(carpeta, "describir.json")
    voz, sam = _leer(carpeta, "transcribir.json"), _leer(carpeta, "sam.json")
    salida = []

    def anotar(rid: str, cumple: bool | None, evidencia: str) -> None:
        r = reglas[rid]
        salida.append({"id": rid, "ventana": r["ventana"], "regla": r["regla"], "cumple": cumple,
                       "evidencia": evidencia, "fuente": r["fuente"]})

    if man and desc:
        t3 = _tramos_hasta(man, desc, 3)
        ganchos = [t for t in t3 if t["tipo_de_gancho"] not in ("ninguno", "presentacion_del_talento")]
        if ganchos:
            g = ganchos[0]
            donde = f"«{g['texto_en_pantalla'].strip()}»" if g["texto_en_pantalla"].strip() else g["que_pasa"].rstrip(".")
            evidencia = f"En el segundo {g['inicio_s']:.0f} abre con {GANCHOS.get(g['tipo_de_gancho'], 'un gancho')}: {donde}."
        else:
            evidencia = f"En los primeros 3 segundos no hay gancho: {t3[0]['que_pasa']}" if t3 else "Sin descripción del inicio."
        anotar("gancho_3s", bool(ganchos), evidencia)
        texto = [t for t in t3 if t["texto_en_pantalla"].strip()]
        voz_s = voz["arranque_voz_ms"] / 1000 if voz and voz.get("arranque_voz_ms") is not None else None
        pronto = bool(texto) or (voz_s is not None and voz_s <= 3)
        partes = []
        if texto:
            partes.append(f"texto en pantalla desde el segundo {texto[0]['inicio_s']:.0f}")
        if voz_s is not None:
            partes.append(f"la voz empieza en el segundo {voz_s:.0f}")
        anotar("mensaje_3s", pronto, ("; ".join(partes)[:1].upper() + "; ".join(partes)[1:] + ".") if partes
               else "Ni texto ni voz en los primeros 3 segundos.")
        t10 = _tramos_hasta(man, desc, 10)
        con_texto = sum(1 for t in t10 if t["texto_en_pantalla"].strip())
        anotar("sin_sonido_10s", con_texto >= len(t10) / 2 if t10 else None,
               f"Hay texto en pantalla en {con_texto} de {len(t10)} partes de los primeros 10 segundos.")
        cuarto = _tramos_hasta(man, desc, man["tramos"][9]["fin_s"])
        ajeno = [t for t in cuarto if t.get("riesgo_anzuelo") == "material_ajeno"]
        anotar("original", not ajeno, f"Parece material de otros en el segundo {ajeno[0]['inicio_s']:.0f}." if ajeno
               else "No se ve material de otros.")
    if sam and "aparece" in sam:
        # SAM busca un objeto en inglés; a la persona se le dice en palabras suyas.
        anotar("promesa_3s", bool(sam["aparece"]),
               f"Lo que promete el título se ve desde el segundo {sam['primer_segundo']:.0f} (lo revisó SAM)." if sam["aparece"]
               else f"Lo que promete el título no se ve en los primeros {sam.get('segundos_revisados', 3)} segundos (lo revisó SAM).")
    if man:
        r = _proporcion(carpeta / man["mp4_ligero"])
        if r is not None:
            anotar("vertical", abs(r - 9 / 16) < 0.03, "Vertical 9:16." if abs(r - 9 / 16) < 0.03
                   else f"Proporción {r:.2f} (vertical sería 0.56).")
    return salida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("carpeta", type=Path)
    a = ap.parse_args()
    print(json.dumps(revisar(a.carpeta), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
