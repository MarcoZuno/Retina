# Decisiones

Por qué se decidió cada cosa, con fecha. Lo más nuevo va arriba.

## 27-oct-2026

- **2 cuadros por tramo para V-JEPA 2.** El modelo junta los cuadros de 2 en 2
  en el tiempo; con 80 cuadros su salida queda alineada 1 a 1 con los 40 tramos
  de la curva, sin interpolar.
- **Decodificación completa en GPU, no solo cuadros clave.** Los cuadros clave
  vienen cada ~1 s: en videos cortos se repetirían cuadros y se perdería el
  movimiento, que es lo que V-JEPA 2 sabe leer. Cuesta 2x más tiempo; se queda
  la opción `--rapido`.
- **ViT-L (300 M) y no ViT-g.** Cabe holgado en 8 GB en fp16 y corre 1.2 s por
  video. Si el tiempo alcanza, se compara con ViT-g en el día 8.
- **Los créditos no cambian el modelo a contributor.** Los «Hackathon Credit
  Terms» no mencionan entrenamiento con lo que mandamos; el uso se rige por los
  términos del API, donde los modelos Standard no entrenan con las entradas.

## 26-oct-2026

- **El «tramo más común» de la línea base se aprende solo en entrenamiento.**
  Calcularlo con los videos de prueba inflaba el acierto de la regla. Con el
  método limpio la cifra sale distinta a la nota previa al evento; se reporta
  la que salió.
- **El tramo de caída anómala se busca después del primer 10 % del video.**
  Todos los videos pierden gente al arranque; incluirlo premia lo obvio.
- **Cifras fuera del repo hasta tener autorización.** Los resultados viven
  en la carpeta de datos privada; el README se llena el día 8.
- **predecir v0 sin modelos.** Antes de gastar API se mide cuánto se logra con
  lo que ya se sabe antes de publicar. Así se ve cuánto aporta de verdad ver
  el video con los modelos de Meta.
- **Bono de pesos abiertos: necesita Muse Glimmer o Muse Spark Open.** Según
  los organizadores (Discord, 26-oct), ese bono es solo para esos dos modelos
  y el aliado verifica que corran en el proyecto. V-JEPA 2 cuenta como modelo
  de Meta para la etapa 1, pero no para ese bono.

- **Repo nuevo, código escrito desde hoy.** Ningún script anterior al evento
  entra al repo. Los datos previos se declaran en el README como
  «infraestructura y datos previos».
- **40 tramos iguales por video.** La curva de Facebook trae 41 puntos
  (0 % a 100 % de la duración); cada tramo va de un punto al siguiente. Spark
  responde por índice de tramo, no por segundo, porque los tiempos que inventa
  un modelo no son confiables.
- **Audio a 24 kHz, no 16 kHz.** La documentación de Voice Transcribe dice que
  24 kHz es su tasa nativa; 16 kHz también se acepta, pero el servidor la
  remuestrea.
- **El audio va solo por Voice Transcribe.** La documentación de Spark 1.3 dice
  que el audio dentro del video «no está totalmente soportado». Por eso el
  esquema del tramo no tiene voz ni música: solo lo que se ve.
- **MP4 ligero de 480p para la Files API.** Menos bytes que subir y que
  almacenar (tope de 100 GiB por equipo). Se medirá si cambia los tokens.
- **Archivos subidos con caducidad de 1 hora y borrado al terminar.** Por
  omisión la Files API no borra nada.
- **La llave vive fuera del repo** (`un .env fuera del repo` o `RETINA_ENV`),
  nunca se imprime y los errores solo muestran estado y mensaje.
- **Las reglas viven en archivos** (`reglas/`), con versión y fecha. El esquema
  toma sus valores de ahí: cambiar la lista de anzuelos no toca el código.
- **Licencia MIT.** El plan permite MIT o Apache 2.0; MIT es la más corta.
- **README en inglés; BUILD-LOG y decisiones en español** con resumen en
  inglés donde hace falta. El jurado lee el README; el equipo trabaja en
  español.

## 27-oct-2026 · Lo que V-JEPA 2 sí y no hace en Retina

- **Medido, no supuesto.** Con miles de videos de entrenamiento y cientos de prueba,
  el vector de V-JEPA 2 por tramo (y el audio por tramo) no ubica mejor el
  tramo de caída anómala que la posición más común. La posición más común es
  el primer tramo después del gancho.
- **Qué se hace con eso.** El tramo de riesgo del panel sale de la v0 más la
  posición típica de su duración. V-JEPA 2 queda como servicio local (detecta
  cortes y cambios de escena, sin costo) y como insumo para Spark, no como
  predictor del «dónde».
- **Lo que queda por probar.** Que Spark, viendo el video y leyendo la
  transcripción, explique la caída mejor que la regla. Esa es la prueba del
  gate 1 y la historia de la demo: el modelo de pesos abiertos dice dónde
  cambia el video; Spark dice por qué se va la gente.
- **Por qué no se fuerza.** Un número inflado en la demo se cae frente al
  jurado. Se reporta el resultado negativo en el BUILD-LOG.

## 27-oct-2026 · El dato manda: resolución de la curva

- **La curva viene en enteros.** Los exports de Meta redondean cada punto a
  1 %. Pasado el primer cuarto del video, la caída por tramo casi siempre es
  0 o 1 punto. Predecir el tramo exacto ahí es predecir el redondeo.
- **Qué promete Retina.** La curva completa contra videos parecidos, y si el
  gancho o el primer cuarto pierden más gente de lo normal. No promete el
  segundo exacto donde se va la gente pasado el arranque.
- **Toda la data entra.** Se usan todas las curvas desde 2020, aunque no haya
  archivo: sirven para la línea base y para aprender qué de la voz explica el
  arranque. El modelo de metadatos se entrena con los años recientes, porque
  sumar años viejos no lo mejora.
- **Los videos de prueba no cambian** (jul-sep 2026), para comparar contra
  todo lo medido antes.

## 27-oct-2026 (noche) · Qué sí dice el panel

- **El nivel del arranque es la promesa.** Alto, medio o bajo, contra videos
  parecidos. Es lo único que se sostuvo en las dos pruebas (2024 y jul-sep 2026).
- **El bloque no se promete.** Predecir cuál de los cinco bloques pierde más no
  le gana a decir siempre el más común. Se muestra la caída de los parecidos por
  bloque como contexto, y Spark explica qué pasa en el arranque viendo el video.
- **La voz no entra al nivel.** Medido dos veces, con cientos de videos de
  prueba. Va a la explicación de Spark, que sí la lee.

## 28-oct-2026 · Retina como agente

- **El modelo no calcula, interpreta.** El nivel de riesgo sale de código medido; Spark
  nunca lo cambia. Su trabajo es decir qué del arranque lo explica y proponer un cambio.
- **Las herramientas solo leen.** Ninguna escribe, publica ni toca la cuenta de nadie.
  Lo que devuelven (textos en pantalla, frases, títulos de otros videos) es dato, no
  instrucción.
- **El validador manda.** Una tarjeta con una cifra que ninguna herramienta devolvió, un
  segundo fuera del arranque o un anzuelo no se entrega: se le regresa al agente.
- **Siempre hay respuesta.** Si el ciclo no cierra en el tope de turnos, cae a `explicar`
  de una vuelta, que tiene el mismo validador.
- **SAM 3.1 solo sobre objetos y lugares.** Se usa para ver si lo que promete el título
  aparece en los primeros 3 s. Nunca sobre personas.

## 28-oct-2026 · La vara justa: contra videos del mismo tipo

- **Qué cambió.** «Perder de más» se mide contra la regla de hoy corregida por tipo de
  producción, y el modelo aprende contra esa misma regla. Sin la corrección, el «alto»
  premiaba ser de un tipo que casi siempre pierde de más; eso no le sirve a quien edita.
- **Por qué no se quitó el tipo del modelo.** El tipo sigue entrando como rasgo; lo que
  cambia es la vara. Así el nivel dice algo que el tipo solo no dice.
- **«Bajo» no es «va bien».** También en «bajo» hay videos que pierden de más, solo que
  menos. El titular dice «No vemos un problema claro».
- **La tarjeta habla como persona.** Sin porcentajes ni jerga, con segundos, con un solo
  cambio y sin tocar marca, ley ni línea editorial. El validador lo exige.
- **A Meta solo van videos publicados,** y el código lo pide de forma explícita.
