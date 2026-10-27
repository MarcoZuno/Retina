# Decisiones

Por qué se decidió cada cosa, con fecha. Lo más nuevo va arriba.

## 26-oct-2026

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
