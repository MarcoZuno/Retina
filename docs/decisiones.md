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
