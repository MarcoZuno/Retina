# Retina — guía para quien trabaje en este repo (personas o agentes)

Retina revisa un video antes de publicarlo: dice si el inicio va a perder más gente que videos
parecidos, dónde y qué cambiar, en pasos que un editor puede seguir. Código y textos de interfaz en
español de México; README en inglés para el jurado.

## Cómo correr

- Tests (sin llave ni datos): `python -m unittest discover -s tests`. El hook de pre-commit los
  corre con el escáner de secretos; si fallan, no hay commit.
- Demo sin llave: `PYTHONPATH=src python -m retina.demo`.
- Retina completo con la API de Meta: ver README («How to run it with your own key»).

## Dónde está cada cosa

- `src/retina/`: el motor. `retina.py` orquesta; `arranque.py` calcula el riesgo del inicio;
  `agente.py` y `explicar.py` escriben la tarjeta; `integridad.py` y el validador de `explicar.py`
  la revisan; `meta_api.py` llama a Meta con tope de gasto.
- `skills/`: instrucciones de Spark, con versión. Si cambias una, sube la versión.
- `reglas/`: anzuelos que Meta castiga, intocables (logo, pixelados, título, avisos) y lo que SAM
  puede buscar (nunca personas).
- `eval/`: cada medición, con su regla escrita antes de correr en `docs/decisiones.md`.
- `panel/index.html`: lo que ve la persona. Lee `resultado.json` (contrato en `docs/resultado-json.md`).

## Reglas que no se rompen

1. **Nada de datos internos en el repo:** ni curvas por video, títulos, talentos, transcripciones,
   ingresos ni cifras de acierto sin aprobación. Los datos viven fuera del repo.
2. **La tarjeta nunca sugiere trucos que Meta castiga** ni tocar intocables. Eso lo decide el
   código (validador y filtro), no el modelo.
3. **Medir antes de prometer:** una idea nueva entra con su regla de victoria escrita antes de
   correr, y se reporta aunque pierda (BUILD-LOG y `docs/decisiones.md`).
4. **Tope de gasto en código** (`TOPE_MAXIMO_USD` en `meta_api.py`); el `.env` no lo sube.
5. **Candado de borradores:** `RETINA_SOLO_PUBLICADOS=1` por omisión para contenido de empresa.
6. **Solo aportan código los integrantes aceptados del equipo** (reglas del concurso).
7. **En el panel, todo lo que viene del JSON entra como texto** (`textContent`), nunca como HTML.
8. Cada día de trabajo deja su entrada fechada en `BUILD-LOG.md`.
