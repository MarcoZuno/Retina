"""La voz tramo a tramo, a partir de una transcripción con tiempos.

Cada frase trae solo su inicio; se supone que dura hasta que empieza la
siguiente (con tope de 8 s, para no tapar silencios largos). Por tramo de la
curva salen:
  0 palabras por segundo (÷ 4)
  1 fracción del tramo con voz
  2 hay un hueco de 1.5 s o más sin voz
  3 frases que empiezan en el tramo (÷ 3)
  4 hay una pregunta
  5 palabras del tramo contra el promedio del video (log)
  6 cambio de palabras por segundo contra el tramo anterior
  7 el video no tiene voz en este punto todavía (antes de la primera frase)
"""
from __future__ import annotations

import numpy as np

N_TRAMOS = 40
N_RASGOS = 8
TOPE_FRASE_S = 8.0
HUECO_S = 1.5


def rasgos_voz(tramos: list[list], dur: float) -> np.ndarray:
    r = np.zeros((N_TRAMOS, N_RASGOS), dtype=np.float32)
    if not tramos or not dur:
        return r
    frases = sorted((float(t), str(x)) for t, x in tramos if float(t) < dur)
    if not frases:
        return r
    inicios = np.array([t for t, _ in frases])
    fines = np.minimum(np.append(inicios[1:], dur), inicios + TOPE_FRASE_S)
    n_pal = np.array([len(x.split()) for _, x in frases], dtype=float)
    largo = dur / N_TRAMOS
    for k in range(N_TRAMOS):
        a, b = k * largo, (k + 1) * largo
        cruce = np.clip(np.minimum(fines, b) - np.maximum(inicios, a), 0, None)
        dentro = cruce / np.maximum(fines - inicios, 1e-6)
        pal = float((n_pal * dentro).sum())
        voz = float(cruce.sum())
        r[k, 0] = pal / largo / 4
        r[k, 1] = min(voz / largo, 1.0)
        # hueco: algún tramo de 1.5 s sin voz dentro del intervalo
        tapado = sorted((max(s, a), min(e, b)) for s, e in zip(inicios, fines) if e > a and s < b)
        cursor, hueco = a, False
        for s, e in tapado:
            hueco |= s - cursor >= HUECO_S
            cursor = max(cursor, e)
        r[k, 2] = float(hueco or b - cursor >= HUECO_S)
        empiezan = (inicios >= a) & (inicios < b)
        r[k, 3] = empiezan.sum() / 3
        r[k, 4] = float(any("?" in frases[i][1] for i in np.flatnonzero(empiezan | (dentro > 0))))
        r[k, 7] = float(b <= inicios[0])
    media = r[:, 0].mean() + 1e-3
    r[:, 5] = np.log((r[:, 0] + 1e-3) / media)
    r[1:, 6] = r[1:, 0] - r[:-1, 0]
    return r
