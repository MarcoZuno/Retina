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
- Lote completo: casi todos los videos de la lista con vector de V-JEPA 2 y audio por
  tramo (volumen, silencios, cruces por cero). Los 27 restantes no están en
  el archivo de exports.
- Medición del tramo de caída anómala con los videos de prueba que tienen
  vector: ni la imagen (V-JEPA 2 promediado por tramo) ni el audio le ganan a
  «el tramo más común». Ese tramo es casi siempre el primero después del
  gancho (el 10 % inicial). La imagen sí se mueve en la dirección correcta
  dentro de cada video, pero la señal es débil. El audio no agrega nada medible.
- Curvas completas con vectores: iguales a la v0 dentro del intervalo de
  confianza. Leve mejora en el orden de los videos, también dentro del ruido.

**Decisión del día**
- El «dónde» del panel sale del modelo con metadatos más la posición
  típica; V-JEPA 2 se queda como servicio, pero ya no se presume que ubica el
  tramo. El «por qué» y el «qué cambiar» son trabajo de Spark viendo el
  video (gate 1). Ver `docs/decisiones.md`.

**Costo del día:** USD 0.00 (sin llamadas a la API).

### Día 2 (tarde) · toda la data

**Hecho**
- `base.py`: una sola base con todas las curvas de la página desde 2020
  (decenas de miles de producciones con curva de 41 puntos, contra unos pocos miles de la lista
  congelada), el archivo final cuando existe y la transcripción con tiempos
  cuando existe (casi toda la base). Los videos sin archivo se quedan: aportan
  curva y metadatos.
- `voz.py`: lo que se dice tramo a tramo (palabras por segundo, voz contra
  silencio, pausas, arranques de frase, preguntas).
- `transcribir_local.py`: Whisper local para los videos con archivo y sin
  transcripción (solo para entrenar y medir; el panel usa Voice Transcribe).
- La regla de «videos parecidos» ahora usa sumas acumuladas: mismo resultado
  (comprobado en 400 videos), 10 veces más rápida, necesaria para decenas de miles.
- `eval/escala.py`, `eval/voz_tramo.py`, `eval/voz_gancho.py`.

**Medido**
- La curva de los exports de Facebook viene en puntos porcentuales enteros.
  Después del primer cuarto del video, casi todos los tramos pierden 0 o 1
  punto: el tramo exacto de la caída está por debajo de la resolución del
  dato. Eso explica por qué ni la imagen, ni el audio, ni la voz lo ubican.
- Más años de historia no mejoran el modelo de metadatos (la audiencia de
  2020 no es la de 2026).
- La voz del arranque sí mejora la curva, sobre todo a los 3 segundos, y el
  exceso de caída en el gancho se puede anticipar (correlación moderada).
  Medido entrenando con 2020-2023 y probando en 2024.

**Decisión**
- El «dónde» de Retina pasa de «tramo exacto» a «el gancho / el primer cuarto
  pierde más que tus videos parecidos», que es lo que el dato sí sostiene.
  Ver `docs/decisiones.md`.

**Costo:** USD 0.00 (todo local).

### Día 2 (noche) · Gate 1 con la API real

**Medido** (un video ya publicado de 100 s, modo Standard, tope del día USD 10)
- Ping a Spark desde México: 1.6 s.
- Voice Transcribe: 100 s de audio en 58 s, USD 0.005.
- Describir (Spark ve el video, 40 tramos, 0 errores de validación): 21,061 tokens
  de entrada, 6,285 de salida, 34 s, USD 0.053. Leyó exacto el texto en pantalla.
- Explicar el tramo de riesgo: 12 s, USD 0.015, con un cambio concreto y lo que no pudo
  verificar.
- **Trampa:** `/v1/responses/input_tokens` no cuenta el video (dio 1,343 contra 21,061
  cobrados; ~200 tokens por segundo de video). `describir.py` ya lo suma antes de revisar
  el tope.
- Costo de punta a punta: ~USD 0.075 por video de 100 s.
