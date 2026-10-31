"""Las demás métricas de Meta de cada video: alcance, reacciones, compartidos, tiempo visto y de dónde
vinieron las reproducciones (recomendaciones de Facebook, seguidores o contenido compartido).

Lee los mismos CSV que cualquier página baja de Meta Business Suite y se
queda, por publicación, con la misma fila que la base: la de curva más completa y más vistas.

Nunca lee columnas de ingresos ni de monetización: se descartan del encabezado antes de leer las filas,
así que ni se cargan en memoria. Retina no aprende ni reporta dinero.

Uso:
    python -m retina.metricas_meta --exports CARPETA [--exports ...] [--pagina NOMBRE] --salida metricas.csv
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

N_PUNTOS = 41
CURVA = "Porcentaje del total de reproducciones en el intervalo {}"


def _num(valor) -> float | None:
    try:
        return float(str(valor).replace(",", ""))
    except (TypeError, ValueError):
        return None


# nombre en la salida -> nombres posibles en el export (cambian entre años)
METRICAS = {
    "alcance": ("Alcance",),
    "alcance_organico": ("Alcance de Publicaciones orgánicas",),
    "vistas_3s": ("Reproducciones de video de 3 segundos", "Visualizaciones"),
    "espectadores_3s": ("Espectadores de 3 segundos",),
    "vistas_1min": ("Reproducciones de video de 1 minuto",),
    "reacciones": ("Reacciones",),
    "comentarios": ("Comentarios",),
    "compartidos": ("Veces que se compartió",),
    "segundos_vistos": ("Segundos reproducidos",),
    "segundos_promedio": ("Segundos en promedio reproducidos",),
    "seg_recomendaciones": ("Segundos reproducidos en Recomendaciones",),
    "seg_seguidores": ("Segundos reproducidos en Seguidores",),
    "seg_compartido": ("Segundos reproducidos en Contenido compartido",),
    "vistas_1min_recomendaciones": ("Reproducciones de video de 1 minuto de Recomendaciones",),
    "vistas_1min_seguidores": ("Reproducciones de video de 1 minuto de Seguidores",),
    "vistas_1min_compartido": ("Reproducciones de video de 1 minuto de Contenido compartido",),
    "vistas_x": ("Reproducciones de video de 3 segundos de Publicaciones promocionadas",
                     "Visualizaciones de Publicaciones promocionadas", "Views from Publicaciones promocionadas"),
}
PROHIBIDAS = ("ingreso", "monetiz", "revenue", "earning")  # dinero: ni se lee


def columna(cols: list[str], nombres: tuple[str, ...]) -> str | None:
    c = next((n for n in nombres if n in cols), None)
    assert c is None or not any(p in c.lower() for p in PROHIBIDAS), c
    return c


def filas_sin_dinero(h) -> tuple[list[str], "object"]:
    """Encabezado y filas del CSV sin las columnas de dinero: se quitan antes de convertir cada fila."""
    lector = csv.reader(h)
    encabezado = next(lector, [])
    quedan = [i for i, c in enumerate(encabezado) if not any(p in c.lower() for p in PROHIBIDAS)]
    cols = [encabezado[i] for i in quedan]
    return cols, ({c: (fila[i] if i < len(fila) else "") for c, i in zip(cols, quedan)} for fila in lector)


def leer(carpetas: list[Path], pagina: str) -> dict[str, dict]:
    """post_id -> métricas, de la misma fila que elige la base (curva más completa, luego más vistas)."""
    filas: dict[str, tuple] = {}
    for carpeta in carpetas:
        for f in sorted(carpeta.rglob("*.csv")):
            with f.open(encoding="utf-8-sig", newline="") as h:
                cols, r = filas_sin_dinero(h)
                if "Nombre de la página" not in cols or CURVA.format(0) not in cols:
                    continue  # Instagram u otro reporte sin curva
                mapa = {k: columna(cols, v) for k, v in METRICAS.items()}
                for row in r:
                    if (row.get("Nombre de la página") or "").strip() != pagina:
                        continue
                    if (row.get("Tipo de publicación") or "") not in ("Videos", "Reels"):
                        continue
                    completos = sum(_num(row.get(CURVA.format(i))) is not None for i in range(N_PUNTOS))
                    m = {k: (_num(row.get(c)) if c else None) for k, c in mapa.items()}
                    clave = (completos, m["vistas_3s"] or 0.0)
                    pid = row["Identificador de la publicación"]
                    if pid not in filas or clave > filas[pid][0]:
                        filas[pid] = (clave, m)
    return {pid: m for pid, (_, m) in filas.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--exports", type=Path, action="append", required=True)
    ap.add_argument("--pagina", default="Badabun")
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    datos = leer(a.exports, a.pagina)
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    with a.salida.open("w", encoding="utf-8", newline="") as h:
        w = csv.writer(h)
        w.writerow(["post_id", *METRICAS])
        for pid, m in sorted(datos.items()):
            w.writerow([pid, *("" if m[k] is None else m[k] for k in METRICAS)])
    con = {k: sum(m[k] is not None for m in datos.values()) for k in METRICAS}
    print(f"{a.salida}: {len(datos):,} publicaciones · con dato: {con}")


if __name__ == "__main__":
    main()
