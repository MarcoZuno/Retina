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
GANCHOS_EN = {"pregunta": "a question", "dato_impactante": "a striking fact", "promesa": "a promise",
              "conflicto": "a conflict", "imagen_impactante": "an eye-catching image", "otro": "a hook"}
# Las frases de la evidencia, en los dos idiomas del panel.
FRASES = {
    "es": {"gancho": "En el segundo {s:.0f} abre con {g}: {donde}.", "sin_gancho": "En los primeros 3 segundos no hay gancho: {x}",
           "sin_desc": "Sin descripción del inicio.", "texto": "texto en pantalla desde el segundo {s:.0f}",
           "voz": "la voz empieza en el segundo {s:.0f}", "nada": "Ni texto ni voz en los primeros 3 segundos.",
           "sin_sonido": "Hay texto en pantalla en {n} de {m} partes de los primeros 10 segundos.",
           "ajeno": "Parece material de otros en el segundo {s:.0f}.", "propio": "No se ve material de otros.",
           "promesa_si": "Lo que promete el título se ve desde el segundo {s:.0f} (lo revisó SAM).",
           "promesa_no": "Lo que promete el título no se ve en los primeros {n} segundos (lo revisó SAM).",
           "vertical": "Vertical 9:16.", "proporcion": "Proporción {r:.2f} (vertical sería 0.56)."},
    "en": {"gancho": "At second {s:.0f} it opens with {g}: {donde}.", "sin_gancho": "No hook in the first 3 seconds: {x}",
           "sin_desc": "No description of the opening.", "texto": "on-screen text from second {s:.0f}",
           "voz": "the voice starts at second {s:.0f}", "nada": "No text and no voice in the first 3 seconds.",
           "sin_sonido": "There is on-screen text in {n} of {m} parts of the first 10 seconds.",
           "ajeno": "Looks like someone else's footage at second {s:.0f}.", "propio": "No footage from others.",
           "promesa_si": "What the title promises shows from second {s:.0f} (checked by SAM).",
           "promesa_no": "What the title promises does not show in the first {n} seconds (checked by SAM).",
           "vertical": "Vertical 9:16.", "proporcion": "Aspect ratio {r:.2f} (vertical would be 0.56)."},
}


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


def revisar(carpeta: Path, idioma: str = "es") -> list[dict]:
    reglas = {r["id"]: r for r in json.loads(REGLAS.read_text(encoding="utf-8"))["reglas"]}
    F = FRASES["en" if idioma == "en" else "es"]
    tipos = GANCHOS_EN if idioma == "en" else GANCHOS
    man, desc = _leer(carpeta, "manifiesto.json"), _leer(carpeta, "describir.json")
    voz, sam = _leer(carpeta, "transcribir.json"), _leer(carpeta, "sam.json")
    salida = []

    def anotar(rid: str, cumple: bool | None, evidencia: str) -> None:
        r = reglas[rid]
        salida.append({"id": rid, "ventana": r["ventana"], "regla": r.get(f"regla_{idioma}", r["regla"]), "cumple": cumple,
                       "evidencia": evidencia, "fuente": r["fuente"]})

    if man and desc:
        t3 = _tramos_hasta(man, desc, 3)
        ganchos = [t for t in t3 if t["tipo_de_gancho"] not in ("ninguno", "presentacion_del_talento")]
        if ganchos:
            g = ganchos[0]
            donde = f"«{g['texto_en_pantalla'].strip()}»" if g["texto_en_pantalla"].strip() else g["que_pasa"].rstrip(".")
            evidencia = F["gancho"].format(s=g["inicio_s"], g=tipos.get(g["tipo_de_gancho"], tipos["otro"]), donde=donde)
        else:
            evidencia = F["sin_gancho"].format(x=t3[0]["que_pasa"]) if t3 else F["sin_desc"]
        anotar("gancho_3s", bool(ganchos), evidencia)
        texto = [t for t in t3 if t["texto_en_pantalla"].strip()]
        voz_s = voz["arranque_voz_ms"] / 1000 if voz and voz.get("arranque_voz_ms") is not None else None
        pronto = bool(texto) or (voz_s is not None and voz_s <= 3)
        partes = []
        if texto:
            partes.append(F["texto"].format(s=texto[0]["inicio_s"]))
        if voz_s is not None:
            partes.append(F["voz"].format(s=voz_s))
        anotar("mensaje_3s", pronto, ("; ".join(partes)[:1].upper() + "; ".join(partes)[1:] + ".") if partes
               else F["nada"])
        t10 = _tramos_hasta(man, desc, 10)
        con_texto = sum(1 for t in t10 if t["texto_en_pantalla"].strip())
        anotar("sin_sonido_10s", con_texto >= len(t10) / 2 if t10 else None,
               F["sin_sonido"].format(n=con_texto, m=len(t10)))
        cuarto = _tramos_hasta(man, desc, man["tramos"][9]["fin_s"])
        ajeno = [t for t in cuarto if t.get("riesgo_anzuelo") == "material_ajeno"]
        anotar("original", not ajeno, F["ajeno"].format(s=ajeno[0]["inicio_s"]) if ajeno else F["propio"])
    if sam and "aparece" in sam:
        # SAM busca un objeto en inglés; a la persona se le dice en palabras suyas.
        anotar("promesa_3s", bool(sam["aparece"]),
               F["promesa_si"].format(s=sam["primer_segundo"]) if sam["aparece"]
               else F["promesa_no"].format(n=sam.get("segundos_revisados", 3)))
    if man:
        r = _proporcion(carpeta / man["mp4_ligero"])
        if r is not None:
            anotar("vertical", abs(r - 9 / 16) < 0.03, F["vertical"] if abs(r - 9 / 16) < 0.03 else F["proporcion"].format(r=r))
    return salida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("carpeta", type=Path)
    a = ap.parse_args()
    print(json.dumps(revisar(a.carpeta), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
