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

### Día 2 (cierre) · Riesgo del arranque

**Hecho**
- `arranque.py`: dice si el gancho y el primer cuarto van a perder más gente que
  videos parecidos (alto, medio o bajo), con y sin la voz del arranque. Se guarda en
  JSON (no pickle): va al repo público y lo cargan los jueces.
- `retina.py` lo usa: con la API toma la voz de Voice Transcribe; sin la API, solo
  metadatos. `voz.py` convierte los turnos de Voice Transcribe a frases con tiempo.

**Medido** (entrena antes del periodo, prueba en el periodo; cifras en la investigación privada)
- Prueba jul-sep 2026: cuando dice «alto», el arranque sí pierde de más en la gran
  mayoría de los casos; cuando dice «bajo», en la mitad. En 2024, el mismo orden.
- La voz no cambia el nivel de riesgo (sí ayuda a la curva a los 3 s).

### Día 2 (noche) · Base final con toda la voz

**Hecho**
- Whisper local transcribió miles de videos de 2025-2026 que tenían archivo y no tenían voz
  (unas dos horas en la GPU de prototipos). V-JEPA 2 y el audio quedaron para toda la base con archivo.
- Se reentrenó el riesgo del arranque con la voz nueva.
- Arreglo: con la voz apagada para el nivel, `predecir` le pasaba la voz al modelo sin
  voz y tronaba por tamaño de matriz. Ahora solo la recibe el modelo con voz.

**Medido** (cifras en la investigación privada)
- Con cuatro veces más videos con voz en la prueba de jul-sep 2026, la voz sigue sin
  mejorar el nivel de riesgo. El nivel sale sin voz.
- En 2026 la voz tampoco mejora la curva (en 2024 sí, a los 3 s). La v0 sigue ganándole
  a la regla de hoy en las 5 medidas.
- Decir cuál de los cinco bloques pierde más no le gana a decir siempre el más común.
  El panel muestra el nivel del arranque; el bloque va como contexto, no como predicción.
- El tramo exacto con video y audio, ahora con 2024: peor que la posición más común.
  Queda cerrado.

**Costo:** USD 0.00 (todo local).

## Día 3 · mié 28-oct (adelantado la noche del 27)

### Explicar el arranque, Retina como agente y SAM 3.1

**Hecho**
- `explicar` v2: Spark explica el nivel de riesgo del arranque (gancho y primer cuarto),
  no un tramo. Recibe lo que se ve y lo que se dice en el arranque, con sus segundos.
  Un validador en código revisa la respuesta antes de que llegue a nadie: que toda cifra
  salga de los datos, que el segundo señalado caiga dentro del arranque y que no haya
  anzuelos. Si falla, Spark recibe el problema y corrige; si vuelve a fallar, la tarjeta
  sale sin sugerencia y lo dice.
- `agente`: Retina como agente, con el patrón de las recetas de Meta (el código calcula,
  el modelo interpreta, un validador revisa). Herramientas de solo lectura: `ver_arranque`,
  `ver_tramos`, `oir`, `buscar_parecidos`, `medir_lo_prometido` y `entregar_tarjeta`. El
  validador corre dentro del ciclo. Guardas: tope de turnos, llamadas repetidas, tope de
  gasto y respaldo a `explicar` de una vuelta.
- `sam`: SAM 3.1 sobre los primeros 3 s (10 cuadros por segundo, 960 px): si aparece lo que
  promete el título, desde qué segundo y cuánto del cuadro ocupa. Nunca sobre personas: la
  condiciones de uso de Meta prohíben seguir personas entre cuadros y el código rechaza el
  concepto antes de llamar a la API.
- `docs/resultado-json.md`: el contrato del panel, con un ejemplo inventado en
  `casos/demo/resultado.json`.
- `eval/casos_api.py` y `eval/casos_agente.py`: Retina de punta a punta en videos de
  jul-sep 2026 ya publicados, con modelos entrenados solo con lo anterior, y el agente
  sobre los mismos casos.

**Arreglos**
- El tope de gasto se leía al importar, antes del `.env`, y valía el de omisión. Ahora se
  lee en cada revisión.
- Con razonamiento alto, Spark a veces gastaba toda la salida pensando y devolvía texto
  vacío. Ahora hay más espacio de salida y, si llega vacío, se repite pensando menos.
- El orquestador reusa la transcripción y la descripción si el caso ya las tiene.
- La Files API pide una caducidad mínima de 1 h; SAM la usa y borra el archivo al terminar.

**Medido** (cifras en la investigación privada)
- Primer caso de punta a punta: cerca de 8 centavos de dólar y minuto y medio por video
  de 100 s. El agente suma unos 2 centavos y de 4 a 7 llamadas a herramientas.
- En la primera tanda, algunos casos fallaron por la salida vacía de arriba; se repiten
  con el arreglo.

**Costo del día:** dentro del tope de USD 10 (detalle en `costos.jsonl`).

### Día 3 (mañana) · Arreglos de la auditoría

Siete revisores independientes (jurado, ingeniería, producto, datos, seguridad, redes y
negocio) auditaron Retina el 28-oct. Esto se arregló el mismo día:

**El riesgo del arranque, contra una vara justa**
- La regla de hoy no distingue tipos de producción, y un tipo casi siempre perdía de más:
  buena parte del acierto del «alto» venía de ahí. Ahora «perder de más» se mide contra
  la regla corregida por tipo (su exceso medio en los 180 días antes del corte) y el
  modelo aprende contra esa misma regla (`arranque-v2`). La ventaja del «alto» se sostiene
  dentro de cada tipo y con o elegibles (`eval/arranque_privado.py`; cifras en la
  investigación privada).
- Versión pública del modelo sin nombres de talento (`modelos/arranque-v2-publico.json`):
  pierde muy poco contra la privada.

**La tarjeta que ve la persona**
- El validador rechaza jerga y cifras internas («pp», porcentajes, «s0.6», «tramo», nombres
  de herramientas), textos de más de 220 caracteres, valores fuera de catálogo, y un
  anzuelo detectado sin su frase, su segundo y cómo quitarlo.
- Lista de intocables (`reglas/intocables-v1.json`): nunca se sugiere quitar el logo, un
  pixelado, el título, la postura editorial, avisos legales ni créditos.
- «Bajo» ya no dice «va bien»: «No vemos un problema claro en tu arranque».
- Panel de ejemplo rehecho al formato nuevo: titular por nivel, banda del arranque, marca
  del cambio, anzuelo con su segundo, error visible, solo `textContent`. Probado sin
  desborde en 360, 390, 768 y 1280 px.

**Filtros**
- Anzuelos: normaliza letras de otros alfabetos, números que imitan letras y palabras
  partidas; detecta emojis de reacción; suma contenido no original, reacciones
  concretas, sorteos, sacar el video de Facebook y más clickbait. Revisa todo el texto
  sugerido; citar un anzuelo para quitarlo no cuenta.
- SAM 3.1: lista cerrada de objetos y lugares (`reglas/sam-permitidos-v1.json`) en vez de
  bloquear palabras. Personas, partes del cuerpo y oficios se rechazan en código.

**Robustez y gasto**
- El orquestador escribe primero lo gratuito y cada paso de la API cae a «no pude revisar»
  si falla; el agente cae al respaldo ante errores de red; lista cerrada de herramientas.
- Lo pagado se reusa solo si el video es el mismo (huella SHA-256).
- Solo videos ya publicados van a Meta: `--ya-publicado` obligatorio con `--con-api`.
- Reintentos: el archivo se vuelve a abrir en cada intento (antes se mandaba vacío),
  tiempos de espera de 10/300 s, fallas de red reintentadas y `Retry-After` con fecha.
- Tope de gasto con candado de archivo, con el peor caso de cada llamada y con un máximo
  en código que ni el `.env` sube (USD 50).
- `store: false` en todas las llamadas a Spark.

**Tests**
- `tests/test_reglas.py` (21 tests, sin API ni datos): filtros, validador, intocables, SAM,
  silencios, la regla de parecidos rápida contra la definición, el tope y el formato del
  panel. `python -m unittest discover -s tests`.

**Costo:** unos centavos (3 casos reales para probar las instrucciones nuevas).

### Día 3 (tarde) · Juez por pares

¿Mirar el video aporta algo que los datos del video no dan? Spark 1.3 ve el arranque de dos
videos reales del mismo tipo (los 50 casos del gate, publicados jul-sep 2026) y dice cuál
pierde más gente que un video parecido. Sin título ni cifras. Solo pares con diferencia
clara (`eval/juez_pares.py`, `skills/juez.md`).

- **Sesgo de posición.** Con un solo orden eligió el segundo video en 10 de 10. Cada par se
  juzga en los dos órdenes y solo cuenta si elige el mismo video las dos veces.
- **Resultado.** Con veredicto firme acierta como un volado; el modelo de datos acierta
  bastante más en los mismos pares, y cuando no coinciden casi siempre tiene razón el modelo.
  Cifras en la investigación privada.
- **Decisión.** El nivel de riesgo se queda con el modelo. El video entra donde sí sirve: decir
  dónde y por qué, y proponer el cambio. No prometemos que «ver el video» mejore la predicción.
- 11 de 524 juicios fallaron con HTTP 400 (archivo ya caducado al reusarlo); se dejan fuera.

**Costo:** USD 9.08 (524 juicios a unos USD 0.017).

### Día 3 (noche) · Predicción contra realidad y candado

- `eval/prediccion_vs_real.py`: en los 50 casos del gate compara la curva que predijo Retina y la
  regla de hoy contra la curva real (a los 3 s, 15 s, mitad, final y toda la curva) y si el nivel
  del arranque acertó. Retina queda más cerca que la regla en la mayoría de los videos y en los
  cinco puntos. Cifras en el reporte interno.
- El candado de «solo publicados» se vuelve un ajuste (`RETINA_SOLO_PUBLICADOS`, encendido por
  omisión). Retina está hecha para revisar antes de publicar; un creador con su propio video lo
  apaga con `0`.

**Costo:** USD 0.

### Día 3 (noche) · ¿Lo que ya medimos del video mejora el nivel? No. Y la tarjeta trae pasos

- `eval/arranque_con_video.py`: el nivel de hoy contra el mismo nivel más V-JEPA 2, ritmo visual
  y audio del arranque. Regla escrita antes de correr (`docs/decisiones.md`). En jul-sep la
  variante elegida no mejora; las de V-JEPA dieron una pista, y la confirmación en ene-jun 2026,
  con la variante fijada de antemano, tampoco gana. El nivel se queda como está.
- La tarjeta trae `pasos`: de 1 a 4 acciones para el editor, con el validador revisando cada una.
  El panel convierte «segundo 12» en 0:12. Probado en un caso real.
- Filtro de anzuelos: «deja tu» bloqueaba «deja tu explicación»; ahora solo «deja tu comentario»,
  «tu opinión», «tu like».

**Costo:** USD 0.03 (un caso para probar los pasos).

### Día 3 (noche, 2) · Panel del concurso y demo de un minuto

- Panel rehecho para quien edita, a partir de una maqueta: semáforo,
  una cifra «de cada 100», barra del inicio con las partes a revisar, pasos numerados con botón
  para copiarlos, y el detalle (curva, confianza, qué revisó el agente) escondido. Solo
  `textContent`, misma CSP. Sin desborde a 360 px (medido con Playwright).
- `python -m retina.demo`: sirve el repo solo en 127.0.0.1 y abre el panel con un caso. Sin llave,
  sin GPU y sin paquetes extra. Rechaza rutas fuera del repo.
