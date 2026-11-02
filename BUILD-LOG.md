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
  tramo (volumen, silencios, cruces por cero). Los pocos restantes no están en
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
  (decenas de miles de producciones con curva de 41 puntos, contra unos
  pocos miles de la lista congelada), el archivo final cuando existe y la transcripción con tiempos
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

### Día 3 (27-oct, 23:59) · Arreglos de la auditoría

Siete revisiones independientes hechas con agentes de IA, cada uno con un perfil (jurado,
ingeniería, producto, datos, seguridad, redes y negocio), auditaron Retina. Esto se arregló el mismo día:

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

### Día 3 (28-oct, 10:05) · Juez por pares

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

### Día 3 (28-oct, 11:35) · Predicción contra realidad y candado

- `eval/prediccion_vs_real.py`: en los 50 casos del gate compara la curva que predijo Retina y la
  regla de hoy contra la curva real (a los 3 s, 15 s, mitad, final y toda la curva) y si el nivel
  del arranque acertó. Retina queda más cerca que la regla en la mayoría de los videos y en los
  cinco puntos. Cifras en el reporte interno.
- El candado de «solo publicados» se vuelve un ajuste (`RETINA_SOLO_PUBLICADOS`, encendido por
  omisión). Retina está hecha para revisar antes de publicar; un creador con su propio video lo
  apaga con `0`.

**Costo:** USD 0.

### Día 3 (28-oct, 12:22) · ¿Lo que ya medimos del video mejora el nivel? No. Y la tarjeta trae pasos

- `eval/arranque_con_video.py`: el nivel de hoy contra el mismo nivel más V-JEPA 2, ritmo visual
  y audio del arranque. Regla escrita antes de correr (`docs/decisiones.md`). En jul-sep la
  variante elegida no mejora; las de V-JEPA dieron una pista, y la confirmación en ene-jun 2026,
  con la variante fijada de antemano, tampoco gana. El nivel se queda como está.
- La tarjeta trae `pasos`: de 1 a 4 acciones para el editor, con el validador revisando cada una.
  El panel convierte «segundo 12» en 0:12. Probado en un caso real.
- Filtro de anzuelos: «deja tu» bloqueaba «deja tu explicación»; ahora solo «deja tu comentario»,
  «tu opinión», «tu like».

**Costo:** USD 0.03 (un caso para probar los pasos).

### Día 3 (28-oct, 12:29) · Panel del concurso y demo de un minuto

- Panel rehecho para quien edita, a partir de una maqueta: semáforo,
  una cifra «de cada 100», barra del inicio con las partes a revisar, pasos numerados con botón
  para copiarlos, y el detalle (curva, confianza, qué revisó el agente) escondido. Solo
  `textContent`, misma CSP. Sin desborde a 360 px (medido con Playwright).
- `python -m retina.demo`: sirve el repo solo en 127.0.0.1 y abre el panel con un caso. Sin llave,
  sin GPU y sin paquetes extra. Rechaza rutas fuera del repo.
- Revisión de seguridad automática del commit: la demo servía toda la carpeta del repo y el panel
  aceptaba `?caso=` de otro sitio con una ruta `//dominio`. Ahora la demo solo sirve el panel y
  `casos/<carpeta>/resultado.json`, revisa que la petición venga a 127.0.0.1 o localhost (contra
  DNS rebinding) y no lista carpetas; el panel solo acepta un `resultado.json` de `casos/` del
  mismo sitio, y si la ruta no vale no abre nada. Probado con curl y Playwright.
- `CLAUDE.md` del repo y paquete de despliegue de la demo estática (`deploy/`: Dockerfile con
  nginx, cabeceras de seguridad, solo panel y casos, contenedor de solo lectura, cómo apagarlo).
  No se pudo probar la imagen aquí: esta PC no tiene Docker.
- Los 50 casos del gate, otra vez con el agente y la tarjeta con pasos: 50 de 50 los escribió el
  agente (ninguno cayó al respaldo); 38 traen cambio con sus pasos y 12 no necesitan cambio.
  **Costo:** USD 1.45 (total del proyecto: USD 16.36 de 50).

### Día 3 (28-oct, 13:56) · «Según Meta» por ventanas

- `src/retina/revision_meta.py` y `reglas/recomendaciones-meta-v1.json`: gancho y mensaje en 0-3 s,
  sin sonido en 0-10 s, lo prometido en 0-3 s (SAM), contenido propio y vertical, cada uno con su
  evidencia y la página de Meta que lo respalda. Corre en el orquestador sin llamar a la API.
- En los 50 casos casi todo se cumple; se presenta como buenas prácticas, no como predicción
  (`docs/decisiones.md`). Tests: 26. **Costo:** USD 0.

### Día 3 (28-oct, 14:16–16:49) · Muse Spark Open, validador y panel Liquid Glass

- Conexión con **Muse Spark Open** en la Model API de Baseten, con tope propio (USD 30). No acepta
  modo JSON: el formato va en las instrucciones.
- El validador tumbaba tarjetas que citaban entre comillas el anzuelo que el video ya dice para
  quitarlo. Arreglado: cuenta como quitar si lo citado está en lo que se dice o se ve.
- Una sola vuelta, mismos 50 casos: Spark 1.3 pasa el validador a la primera en 46; Spark Open en 28.
- Panel del concurso con el diseño «liquid glass» (WebGL sobre fondos hechos con Muse Image; sin
  WebGL, CSS), conectado al `resultado.json` real.

### Día 3 (28-oct, 18:08–18:29) · El agente corre en Spark Open

- Spark Open sí hace llamadas a herramientas por Chat Completions. El mismo ciclo del agente
  (herramientas, validador, guardas) corre con Spark 1.3 o con Spark Open; con `abierto+api`, Spark
  1.3 solo rescata si el ciclo de Spark Open no cierra.
- Mismos 50 casos: el agente en Spark Open cerró los 50 solo (0 rescates), 42 corregidos por él
  mismo tras un rechazo del validador, 5.6 turnos, USD 0.038 por video. Pasa a ser el motor por omisión.
- Con razonamiento alto, la tarjeta de una vuelta no mejoró (22 contra 28): ahí se quedó el de fábrica.
- El panel muestra el storyboard dibujado con Muse Image y quién escribió la tarjeta.

### Día 3 (28-oct, 18:56–20:41) · Galería y prototipo para subir un video

- `retina.demo --casos DIR --galeria`: lista los casos de una carpeta fuera del repo (`panel/galeria.html`).
- `retina.app` + `panel/subir.html`: prototipo local para subir un MP4 ya publicado y recibir la tarjeta.
  Probado de punta a punta: 1 min 40 s y USD 0.09.
- Arreglo: un video ya publicado que el modelo tiene en su entrenamiento tronaba al calcular sus
  parecidos; ahora se saca su fila de entrenamiento.

### Día 3 (28-oct, 22:44 en adelante) · Segunda auditoría y arreglos

- Cuatro revisiones con agentes de IA (jurado, seguridad, reproducibilidad, plan). Se reforzó la
  revisión de datos antes de cada commit (`.gitleaks.toml`) y los ejemplos y pruebas usan solo datos inventados.
- Juez ciego de tarjetas (regla escrita antes de medir): prefirió la tarjeta de una vuelta en 27 de 39
  pares firmes y la del agente en 12. No decimos que las herramientas mejoren la tarjeta
  (`docs/decisiones.md`). **Costo:** USD 0.80.
- Aviso visible de «ejemplo inventado» en el panel, README corregido (lo que no es de Meta, tabla de
  modelos, 50 casos que no son prueba limpia), dependencias fijadas, cabeceras de seguridad en la demo.

### Día 4 (29-oct) · Subir el video en el mismo panel

- `retina.app` abre el panel de siempre (Liquid Glass) con una pantalla para subir el MP4, el avance
  paso a paso y la tarjeta al final, en español e inglés. Sin `retina.app` (la demo sin llave), el
  panel sigue abriendo solo revisiones ya hechas.
- El código de producción es opcional: un video de otra cuenta se puede revisar. Arreglo: sin código,
  el título ya no se partía letra por letra al buscar sus palabras.
- Fuera del repo: `panel/subir.html` y la galería de casos reales (`panel/galeria.html`,
  `--galeria`, `casos/indice.json`). La galería queda en la carpeta privada del equipo.
- El candado de «solo publicados» lo decide el `.env` de quien corre Retina; la página manda si el
  video ya está publicado y el servidor decide.

### Día 4 (29-oct, tarde) · Comparar dos versiones y tarjetas con más detalle

Retro de la primera prueba con una editora: quiere comparar dos versiones del mismo video y, en las
tarjetas verdes, saber qué está bien, qué está flojo y qué más se puede mejorar.
- Tarjeta: `lo_bueno` (1 a 3), `lo_flojo` (0 a 3) y `mejoras_opcionales` (0 a 3) en todos los niveles,
  con el mismo validador (jerga, cifras, anzuelos, intocables). Instrucciones explicar-v6 y agente-v3.
- `retina.comparar` + `skills/comparar.md`: Spark Open (rescate de Spark 1.3) compara cómo arranca cada
  versión con lo que Retina ya vio; juzga en los dos órdenes y solo hay ganadora si coinciden. La app
  compara al terminar la versión B (`X-Retina-Comparar-Con`) y el panel muestra veredicto, tabla y
  diferencias. Los números de retención no deciden: casi no cambian entre cortes del mismo video.
- Medido en la prueba: el mismo video revisado dos veces puede salir descrito distinto; juzgar en los
  dos órdenes quita el sesgo de posición, no ese ruido. Por eso una ganadora necesita al menos una
  diferencia que se sostenga en los dos órdenes.

### Día 4 (29-oct, noche) · Retina para cualquier video

- Pregunta de Jossafat: Retina es para el público en general; con un video de cualquier creador debe
  funcionar, y lo de Badabun debe sumar, no limitar. Hasta hoy el nivel usaba el talento, el tipo de
  producción y el nombre del archivo de la casa; con un video de fuera quedaba casi en el promedio de su
  duración.
- `eval/cualquier_video.py`: se esconden grupos completos de talentos (entrenamiento e historia) y sus
  videos entran como uno de fuera. Regla escrita antes de medir (`docs/decisiones.md`). En jul-sep el
  cerebro para cualquier video gana en todo, pero con intervalos sueltos no pasa la regla; la
  comparación pareja se escribió antes de correrla y se confirmó en ene-jun 2026: pasa.
- `predecir.py`: `fijos_universales` y `rasgos_universales` (duración, reel, hora y día, título, voz
  del arranque y sus primeras 25 palabras), `Modelo.de_la_casa` y el cerebro `universal` dentro del
  modelo, entrenado con toda la historia. La prueba usa estas mismas funciones (da los mismos números).
- `voz.en_bloques`: la voz de Voice Transcribe viene frase por frase; las transcripciones con que se
  entrenó vienen en bloques de ~28 s. Se juntan igual para que los rasgos midan lo mismo.
- `retina.py`: el reel se reconoce por el primer cuadro (vertical) y, con un video de fuera, la curva se
  recalcula en cuanto llega su voz. `licencia` trae `conoce_al_creador` y `cerebro`; el panel avisa
  «Retina todavía no conoce a este creador» en español e inglés.
- Pruebas: 104 (6 nuevas: quién usa cada cerebro, sin voz, nombre de archivo de la casa, bloques de
  voz, reel).

**Costo:** USD 0 (sin llamadas a la API).

### Día 4 (29-oct, noche) · El cerebro público: Retina sin los datos de Badabun

- Riesgo: que el repo fuera una herramienta interna. Era cierto: para revisar un video, la app
  pedía el modelo con la historia de curvas, el riesgo y las transcripciones, todo privado.
- `retina.publico`: arma `modelos/retina-publico.json` (0.8 MB), lo aprendido de la retención sin ningún
  video: pesos del cerebro para cualquier video, el riesgo del arranque sin talento ni tipo de producción y
  cinco curvas promedio por duración. No aprende de videos no elegibles (o sin dato de elegibilidad), de temas
  fuera de alcance ni graves (`reglas/alcance-v1.json`, título y primeras palabras dichas) ni de nombres
  de talentos (lista de talentos y firmas al final de los títulos). JSON, no pickle.
- `retina.app` y `retina.retina` corren solo con ese archivo: `--arranque` y `--voz` ya son opcionales;
  sin las transcripciones de la casa, la tarjeta es de una vuelta. La lista de talentos sale vacía.
- Medido con talentos escondidos (regla escrita antes): le gana a la curva fija por duración y empata con
  la v0 de la casa con los campos vacíos.
- Prueba en limpio: copia del repo en otra carpeta, sin acceso a nada privado, solo con la llave. Un video
  entró como de fuera y salió la tarjeta completa (cerebro para cualquier video, riesgo, Spark Open).
- Pruebas: 114 (10 nuevas en `tests/test_publico.py`: qué queda fuera, nombres, que el archivo no traiga
  textos de ningún video, que abra sin pickle).
- El archivo sigue fuera del repo (`.gitignore`) hasta tener autorización para publicar lo aprendido.

**Costo:** unos USD 0.02 (una tarjeta en la prueba en limpio).

### Día 4 (29-oct, noche) · Una app para cualquiera, en su idioma

- `python -m retina.app` ya arranca sin argumentos: cerebro público y revisiones en `mis-revisiones/`
  (fuera del repo). Sin talentos en el modelo, el formulario solo pide video, título y cuándo saldría.
- Idioma de punta a punta: el panel manda `X-Retina-Idioma`; `describir`, `explicar` (v7), `comparar` (v2)
  y la revisión de Meta escriben en inglés o español. La frase de «contra qué se comparó» y lo que no se
  revisó se arman en el panel, en su idioma.
- `sam.objeto_del_titulo` + `medir_promesa`: SAM corre también sin agente (Spark elige el objeto de la lista
  cerrada). Probado: «tortilla», «dog», «house», y «ninguno» cuando el título no promete nada visible.
- `POST /api/storyboard/<id>`: Muse Image dibuja el storyboard cuando la persona aprieta el botón; una sola
  vez por tarjeta, uno a la vez, solo desde la propia página.
- Plan B (`RETINA_SOLO_MODELOS_META=1`): sin pesos ajustados ni nivel; estado «Revisión» en el panel.
- Pruebas: 120. Prueba en limpio en inglés (con y sin plan B) y storyboard desde la app.

**Costo:** unos USD 0.20 (revisiones de prueba en limpio, una descripción nueva en inglés, SAM y un storyboard; parte del registro de las pruebas en limpio se perdió al rehacer la copia).

### Día 4 (29-oct, noche) · La auditoría del plan, aplicada

- Dos auditores independientes leyeron el plan hasta el 4-nov (como jurado y buscando cómo refutar los
  resultados). Lo que encontraron y se arregló hoy:
  - el candado viene apagado por omisión;
  - cada quien lleva su propio registro de gasto (el del equipo pasó a `docs/costos-equipo.jsonl`);
  - el archivo público ya no trae conteos;
  - las columnas de ingresos ni se cargan en memoria;
  - el README ya no promete un agente ni «videos parecidos» en la versión pública;
  - en las pruebas, solo nombres inventados.
- Modo sin cerebro: si el repo no trae `modelos/retina-publico.json`, Retina revisa igual el video, sin número.
- Semáforo con videos de fuera (`eval/semaforo_publico.py`): regla sellada con commit antes de correr y su huella
  en la bitácora. Distingue, pero en una prueba marcó demasiados videos en «alto»: el modo público no lo muestra.
- Ingresos, nombres reales y conteos revisados en todo lo que entra al commit.

**Costo:** unos USD 0.05 (una revisión sin cerebro, en limpio).

### Día 4 (29-oct, noche) · Retina lee el inicio (con los créditos nuevos)

- Investigación de otras herramientas y de métodos (SnapUGC 2025,
  anuncios 2026). Lo que mejor funciona en la literatura: un modelo multimodal llena una ficha fija del inicio y
  un modelo pequeño aprende de ella. Las herramientas comerciales no publican validación; Retina sí.
- `retina.ficha`: Muse Spark Open anota el arranque (gancho, se presenta antes del tema, tema en la primera
  frase, promesa, cifra, interacción, claridad, curiosidad, emoción) en lotes de 20 videos por llamada. Toda la base desde 2022,
  sin un lote fallido. Esa base se anotó sin temperatura fija; la temperatura 0 (para que el mismo video dé la
  misma ficha) entró después, y la app pide un video a la vez. La ficha que corre en la app no es idéntica a
  la que se midió, y esa diferencia no se ha medido.
- Regla sellada con commit (8fcfaac) antes de medir; pasó en dos periodos: la ficha entra al cerebro público.
- La tarjeta muestra cómo arranca el video y qué pasó con videos que arrancan igual (solo lo que tuvo un
  intervalo lejos de cero, en palabras). También franjas de lo bueno y lo flojo en la línea del tiempo y un
  botón para bajar el resumen para el editor.
- Pruebas: 131.

**Costo:** unos USD 18 de Baseten (la ficha de toda la base) y centavos de Meta en pruebas en limpio.


### Día 4 (29-oct, noche) · La auditoría a fondo, aplicada

Una auditoría con cinco revisores independientes (jurado, fugas, juez que baja el repo, rigor y código) atacó
todo Retina. Lo que se corrigió:

- **El semáforo v2 no entra.** Pasó su regla, pero se escribió después de ver fallar la v1, en los mismos periodos
  ya usados varias veces: por nuestra propia regla, eso es un reajuste. El modo público sigue sin semáforo. Solo
  entraría con una prueba hacia adelante en videos que todavía no existen (regla en `docs/decisiones.md`).
- **Nada sin validar llega a la tarjeta.** Si el validador la rechaza dos veces, sale vacía, con el aviso. Lo que se
  propone decir entre comillas («Reemplaza el saludo por "Comenta SÍ abajo"») se revisa igual que lo demás.
- **Reglas en inglés.** Los anzuelos y los intocables ya se atrapan en inglés («comment YES below», «tag a friend»,
  «link in bio», «remove the logo», «cut the health warning»), y también las cifras escritas con letra.
- **SAM con lista cerrada de verdad:** cualquier palabra de persona, en español o en inglés, se rechaza por
  cualquier camino.
- **Tope de gasto con candado real:** el costo se aparta antes de llamar, con un candado entre procesos; un tope
  escrito mal no lo anula; Baseten respeta el tope del usuario; una llamada pagada siempre queda anotada.
- **El agente tiene límites** de llamadas por turno, por revisión y a SAM.
- **La ficha** ya no lee «false» como verdadero.
- **Lo que ve quien baja el repo:** el `.env` de la raíz se lee; si falta ffmpeg o la llave, la página lo dice al
  abrir y en su idioma; un video sin audio se revisa con lo que se ve; un archivo sin imagen se rechaza; videos de
  hasta 30 minutos, con ffmpeg que nunca se queda colgado; la voz se escucha hasta el minuto 10 y lo dice; si el
  servidor se cae, el panel avisa en vez de esperar para siempre; sin errores en la consola.
- **Idioma:** la voz se pide en inglés cuando el título está en inglés, y la tarjeta avisa que el número es una
  referencia más débil fuera del español. También avisa con reels, que casi no hubo en la base.
- **El ejemplo** se ve como la versión pública: sin semáforo, sin talento y con la ficha del arranque.
- **Textos honestos:** el README ya no exagera (pesos aprendidos con datos privados, qué se midió en qué periodo,
  dónde el cerebro público pierde, el semáforo sin talentos escondidos), trae una captura, un resumen en inglés de
  las reglas selladas y una sección para probarlo con tu video que sí corre desde una copia limpia. La ficha se
  anotó sin temperatura fija: ya lo dice.
- **Datos que no salen:** conteos y cifras de acierto pasados a palabras, sin nombres de fuera del equipo ni el
  prefijo de un tipo de producción, y un escáner más estricto (códigos de 6 a 9 dígitos, también pegados a «_»).
- Pruebas: 183.

**Costo:** USD 0 (ninguna llamada a las API).

## 30-oct-2026 · Retina predice, revisa normas y arregla el arranque

Los organizadores contestaron: la fórmula se vale si está documentada, y una idea cercana a «simple image analyzers» se vale si el
centro es nuevo. Se construyó el lazo de la apertura (Spark Open escribe, reglas de código revisan, Muse Image dibuja, SAM 3.1 comprueba,
hasta 2 correcciones). La primera medición sellada no pasó (10 de 18). Se calibró el vocabulario de SAM y la segunda, con 30 videos
nuevos, pasó (29 de 30). Se probó volver a predecir con el arranque nuevo y no sirvió: el número no compara versiones de un video.
Se sumaron la revisión de normas de Facebook y la demo en línea con código de acceso, y se quitó el cruce de fondos que parpadeaba.

**Auditoría del mismo día.** Cinco revisiones rechazaron la entrega como estaba. Se corrigieron las frases que no se sostenían, el número ya cuenta
desde los 3 segundos y trae su margen medido, el README bajó a una página con anexos en inglés, y salieron unas 20 fallas de código. El arranque pasó a
apertura-v2: da la primera prueba y deja lo demás al video, y el código ya no le ordena al dibujo lo que SAM va a buscar. La tercera medición, con 50 videos
nuevos, regla sellada y juez ciego, pasó sus seis condiciones. Costo de esa medición: USD 3.00, más el juez.

## 31-oct-2026 · Las correcciones de la revisión final y la cuarta medición

Una revisión a fondo de la entrega dejó una lista larga y se corrigió de una pasada. El inicio nuevo pasó a apertura-v3: no enumera todo, conserva la autoridad de
quien habla, Muse Spark 1.3 revisa los cuadros que SAM no ve y Spark Open puede decir que el inicio ya funciona. Nuevos: aviso cuando el video no cumple el título,
aviso de a dónde sale el video y cuánto cuesta, y la historia de correcciones a la vista. El panel abre en el idioma del navegador y los textos ya no dan a entender
que el número es del inicio nuevo. Se endureció el despliegue y se quitaron pesos que el público no usa. La cuarta medición, con 50 videos nuevos y regla sellada, pasó
sus nueve condiciones, con control negativo del juez. La trampa cercana bajó a 7 de 10 y se reporta. Costo: USD 4.12 más el juez.

## 31-oct-2026 · apertura-v4 y la quinta medición

Una revisión con ojos de jurado encontró cuatro cosas que cambiaban el producto: Retina reescribía fuera de alcance y salud, nada en el producto frenaba una apertura infiel, y pasaban saludos y aperturas
de 18 palabras. El inicio pasó a apertura-v4: Muse Spark 1.3 decide antes de gastar si el video es de fuera de alcance o de consejos de salud, lee cada apertura contra lo que dice el video antes de dibujarla, una
regla de código rechaza saludos y el mínimo sube a 25 palabras. El panel pone el inicio arriba del número, avisa cuando un resultado salió incompleto y dice qué es inventado en el ejemplo. El ejemplo se
rehízo con el lazo real y el número real. La quinta medición, con 50 videos nuevos, regla sellada y las mismas nueve condiciones, pasó a la primera: 25 de 30, 18 de 20, 10 de 10, 42 de 43, 42 de 43,
35 de 37, 10 de 10, 8 de 10 y 0 de 50. Trampa cercana 8 de 10. De 234 títulos revisados, 125 quedaron fuera por tema. Costo: USD 4.82 más el juez.

## 31-oct-2026 · Antes de abrir el repo

Una revisión de seguridad no halló fallas críticas ni altas, y se corrigió lo que dejó. El título de un archivo ya no puede colgar el servidor ni fingir que el archivo trae video: se dejó
de buscar con una expresión regular en la salida de ffmpeg. Lo que la tarjeta dice que no pudo verificar pasa ahora los mismos filtros que el resto. El proxy de ejemplo manda de http a https.
Se agregó SECURITY.md para reportar fallas en privado. El filtro de enlaces reconoce más dominios, y las imágenes de Docker y las dependencias indirectas de la demo en línea quedaron con versión fija y huella.

## 2-nov-2026 · Auditoría externa con Codex y correcciones

Un modelo de fuera (Codex, de OpenAI, en solo lectura) auditó el repo y dejó 12 hallazgos; 10 aplicaban a esta copia y se corrigieron el mismo día. Lo que cambia el
producto: una comprobación que no pudo correr ya no deja pasar la apertura (sale sin aprobar, dice qué faltó y se puede volver a pedir), y cada dibujo aparta su precio
con el candado del tope antes de llamar. Además: intocables en el storyboard y en lo traducido, el idioma por nombre en el paso del agente, el título entra en la clave
de reuso de la carpeta, ffmpeg siempre por el mismo envoltorio, el destino de la llave por host exacto y, en línea, el código también para leer un caso subido. El margen
se volvió a medir con las funciones reales del cerebro público: 10.0 y 10.6 de cada 100 (la curva de su duración, 12.2 y 11.5); el panel sigue diciendo «más o menos 11».
La segunda pasada de Codex sobre la versión corregida dio 9 de 12 corregidos, 3 a medias y 3 nuevos, y también se arreglaron: cada intento que pudo cobrarse
(un 5xx o una falla de red, en Meta y en Baseten) aparta lo suyo y la estimación de entrada cuenta todo lo que viaja, también herramientas; el generador suelto de
storyboard frena intocables; una traducción no puede volver recomendación una cita que se manda quitar; una diferencia de la comparación solo se sostiene con el mismo
aspecto en los dos órdenes, nunca por su posición; el README instala desde `requirements.lock` con hashes y ya no dice que el filtro de temas corre antes que todo.
Pruebas: 550. **Costo:** USD 0 (ninguna llamada a las API; el margen corre con datos locales).
