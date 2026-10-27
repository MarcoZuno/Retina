# BUILD-LOG

Diario fechado de construcción: una entrada por día, con lo que se hizo, lo que
se midió y el costo del día. Es la prueba de que Retina se construyó durante el
evento (26-oct → 4-nov-2026).

*Dated build diary, one entry per day: what was built, what was measured, and
the day's cost in USD.*

## Día 1 · lun 26-oct-2026

**Hecho**
- Repo nuevo `retina` con la estructura del plan: README, BUILD-LOG, decisiones,
  reglas fuera del código, skills por estación, `.env.example`, licencia MIT.
- `meta_api.py`: envoltorio único de la Meta Model API. Registra modelo, tokens,
  segundos y USD en `costos.jsonl`; frena al llegar al tope del proyecto
  (USD 100); reintenta 429 respetando `Retry-After`; la llave solo se lee de un
  `.env` fuera del repo.
- `segmentar.py`: MP4 → 40 tramos alineados a los 41 puntos de la curva, cuadros
  a 4 fps (lado corto 256 px), WAV mono 24 kHz para Voice Transcribe y un MP4
  ligero de 480p para la Files API.
- `esquemas.py` + `esquemas/tramo-v1.json`: esquema JSON estricto del tramo
  (sin campos extra, todos obligatorios, valores cerrados). Los valores de
  `riesgo_anzuelo` se leen de `reglas/anzuelos-v1.json`.
- `describir.py` (Spark 1.3 por Files API, salida estructurada por índice de
  tramo), `transcribir.py` (Voice Transcribe, turnos y silencios) y `gate1.py`
  (llamada real y costo de un video).

- `curvas.py`: carga de curvas, regla «videos parecidos» y las cinco métricas
  del plan con intervalo de 95 %, compartidas por la línea base y el modelo.
- `eval/linea_base.py`: la regla de hoy medida en los videos de prueba.
- `predecir.py` v0: regresión ridge sobre la regla de hoy con lo que se sabe
  antes de publicar (duración, tipo de producción, talento, hora, día y
  palabras del título). Sin modelos todavía; es el piso que la versión con
  V-JEPA 2 y Spark tiene que superar.

**Medido**
- `segmentar` sobre un video ya publicado de 99.8 s: 40 tramos de 2.49 s,
  399 cuadros, ningún tramo vacío, MP4 ligero de 3.1 MB, 39 s en total.
- Esquema `tramo-v1` validado contra las reglas del modo estricto.
- Línea base y v0 medidas en los videos de prueba. La v0 mejora a la regla
  en el error a 3 s, 15 s, mitad y final y en el orden de los videos, pero NO
  en ubicar el tramo de caída anómala (ahí queda peor que adivinar el tramo
  más común): sin ver el video no se puede. Las cifras quedan fuera del repo
  hasta tener autorización para publicarlos.

**Pendiente del gate 1**
- Llamada real a Spark desde México y costo de un video: falta la llave del
  equipo.
- Reglas Oficiales leídas y guardadas en `docs/`.

**Costo del día:** USD 0.00 (sin llamadas a la API todavía).

## Día 2 · mar 27-oct-2026

**Hecho**
- `embeber.py`: V-JEPA 2 (ViT-L, pesos abiertos de Meta) corriendo local en una
  tarjeta local. Se toman 80 cuadros por video (2 por tramo); como el modelo agrupa
  los cuadros de 2 en 2, su salida trae exactamente 40 posiciones temporales:
  un vector de 1,024 números por tramo de la curva.
- Lote reanudable: 3 lectores de video en paralelo mientras la GPU corre el
  modelo; un video malo no detiene el lote.
- `predecir.py` v1: sobre la v0, un modelo por tramo con los vectores de
  V-JEPA 2 (qué se ve, cuánto cambió contra el tramo anterior, dónde está)
  aprende la caída que la v0 no explica.

**Medido**
- Decodificar 80 cuadros de un export de 100 s a 1080x1920: 10 s en CPU,
  7.4 s en la GPU (NVDEC), 3.1 s leyendo solo cuadros clave. La red no es el
  cuello de botella (250 MB en 2.9 s).
- V-JEPA 2: 1.2 s por video en la GPU. En lote, 4.5 s por video de punta a punta.
- Los vectores de tramos vecinos se parecen en promedio 0.88 (coseno) y caen
  en los cortes de escena: el modelo sí ve dónde cambia el video.
