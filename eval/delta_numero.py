"""Exploratorio, sin retención real: si Retina predice antes y después de reescribir el arranque, ¿qué pasa con el número?

Solo responde si el número se mueve y hacia dónde. No demuestra que la gente se quede más. Corrió sobre las aperturas de la
primera medición (41 aprobadas). Necesita la carpeta privada de casos y la de esa medición; a la consola solo salen promedios.

Uso (desde la raíz del repo):
    python eval/delta_numero.py CARPETA_CASOS_API CARPETA_DE_LA_MEDICION
"""
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "src"))
from retina import meta_api  # noqa: E402
from retina.curvas import cubeta  # noqa: E402
from retina.ficha import ficha_de  # noqa: E402
from retina.publico import cargar_modelo  # noqa: E402

meta_api._cargar_env()
m = cargar_modelo(R / "modelos" / "retina-publico.json")
casos, medidos = Path(sys.argv[1]) / "casos", Path(sys.argv[2]) / "casos"


def uno(d: Path):
    s = json.loads((d / "apertura.json").read_text(encoding="utf-8"))
    if not s["aprobada"]:
        return None
    t = json.loads((d / "transcribir.json").read_text(encoding="utf-8"))
    tramos = [[x["startMs"] / 1000, x["transcript"]] for x in t.get("turnos", []) if x.get("transcript")]
    if not tramos:
        return None
    dur = json.loads((d / "manifiesto.json").read_text(encoding="utf-8"))["duracion_s"]
    titulo = json.loads((casos / d.name / "resultado.json").read_text(encoding="utf-8"))["video"]["titulo"]
    nuevo = [[0.0, s["despues"]["voz"]]] + [x for x in tramos if x[0] >= 15]
    v = {"fecha": datetime(2026, 10, 30, 18, 0), "dur": dur, "codigo": "", "talento": "", "archivo": titulo, "titulo": titulo,
         "reel": 0.0, "cubeta": cubeta(dur)}
    a = m.predecir(v, None, None, tramos, ficha_de(titulo, tramos))
    b = m.predecir(v, None, None, nuevo, ficha_de(titulo, nuevo))
    i = min(40, round(15 / dur * 40))
    return (a["curva_predicha"][i] * 100, b["curva_predicha"][i] * 100, a["curva_parecidos"][i] * 100)


with ThreadPoolExecutor(4) as h:
    filas = [f for f in h.map(uno, sorted(medidos.iterdir())) if f]
dif = [b - a for a, b, _ in filas]
print(json.dumps({"n": len(filas), "suben": sum(x > 0.5 for x in dif), "bajan": sum(x < -0.5 for x in dif),
                  "casi_igual": sum(abs(x) <= 0.5 for x in dif), "media_dif": round(statistics.mean(dif), 2),
                  "mediana_dif": round(statistics.median(dif), 2), "min": round(min(dif), 1), "max": round(max(dif), 1),
                  "antes_media": round(statistics.mean(a for a, _, _ in filas), 1), "promedio_duracion": round(statistics.mean(c for _, _, c in filas), 1)}))
