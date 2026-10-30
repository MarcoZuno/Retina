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

## 28-oct-2026 · El nivel de riesgo no lo decide Spark mirando el video

- **Qué se probó.** Un juez a ciegas: Spark ve dos arranques reales del mismo tipo y dice cuál
  pierde más gente. Cada par en los dos órdenes, porque con uno solo elegía siempre el segundo.
- **Qué salió.** No le gana al azar y el modelo de datos le gana en los mismos pares.
- **Qué se decide.** El nivel sale del modelo; Spark explica y propone. Es mejor reportar lo que
  no funcionó que prometer que «ver el video» predice.

## 28-oct-2026 (noche) · Regla escrita ANTES de medir si el video mejora el nivel

Prueba gratis (`eval/arranque_con_video.py`): el modelo de hoy (arranque-v2, sin voz) contra el
mismo modelo más un ajuste con lo que ya se mide en local del arranque (V-JEPA 2 de los tramos 0-9
resumido, cambio visual entre tramos como ritmo, y audio por tramo).

- Entrena con lo publicado antes del 1-jul-2026; prueba en jul-sep 2026 con los videos que
  tengan vectores, **sin los 50 casos del gate** (con ellos se afinaron instrucciones).
- Todo se elige con entrenamiento (castigo del ajuste con el último 20 % por fecha).
- **Una sola comparación principal:** correlación entre el exceso predicho y el real del
  arranque, en los mismos videos, con y sin el ajuste. Remuestreo de 2,000.
- **Gana** si la mejora es mayor que cero en el lado pesimista del intervalo del 95 %. Si no,
  el nivel se queda como está y se reporta. Se reportan todas las variantes probadas.

**Resultado (28-oct, noche): no gana con la regla.** La variante que eligió la validación
(ritmo visual) no mejoró nada. Las variantes con V-JEPA sí subieron la correlación en la prueba,
pero no fueron las elegidas, así que eso es una pista, no un resultado.

**Confirmación escrita antes de correr:** variante fija «V-JEPA, PCA de 32», el castigo se elige
igual que antes con entrenamiento. Entrena con lo publicado antes del 1-ene-2026 y prueba en
ene-jun 2026, una ventana que no se había usado como prueba. Misma comparación y misma regla:
gana si la mejora es mayor que cero en el lado pesimista del intervalo del 95 %.

**Resultado de la confirmación (28-oct, noche): no gana.** En ene-jun 2026 la variante fijada no
mejora la correlación (el intervalo cruza el cero). Con esto son cuatro pruebas de «mirar el video
para predecir» que no ganan: voz (dos veces), juez por pares y lo que ya mide V-JEPA en local.
- **Qué se decide.** El nivel se queda con el modelo de datos. La ficha de hechos con Spark (A
  del plan, unos USD 30) no se corre antes del viernes: la prueba gratis era su filtro y no pasó.
- **Dónde sí entra el video:** en explicar dónde y por qué, y en los pasos para arreglarlo.
- **La tarjeta trae «pasos»:** de 1 a 4 acciones en orden para hacer el cambio en el editor, cada
  una con su segundo. El panel muestra los segundos como reloj (0:05).

## 28-oct-2026 (noche) · Revisión «según Meta» por ventanas (idea de la empresa)

- **Qué es.** Revisar desde los primeros segundos lo que Meta recomienda en público: gancho y
  mensaje en los primeros 3 s, que se entienda sin sonido en los primeros 10, que lo prometido se vea
  pronto, contenido propio y video vertical. Cada regla con su fuente (`reglas/recomendaciones-meta-v1.json`).
- **Qué salió en los 50 casos** (`eval/revision_meta_casos.py`): los videos de Badabun ya cumplen casi
  todo (casi todos abren con gancho y mensaje y casi todos se entienden sin sonido). Lo único que separa
  es si lo prometido se ve en los primeros 3 s, y con 10 casos medidos la diferencia no es clara.
- **Qué se decide.** Entra como «Según Meta», buenas prácticas con su segundo y su fuente, sin
  prometer que predicen. Sirve más a un creador que empieza que a un equipo que ya domina lo básico.

## 28-oct-2026 (noche) · ¿Las herramientas mejoran la tarjeta? Regla escrita antes de medir

- **Qué se mide.** En los mismos 50 casos, la tarjeta del agente (Spark Open con herramientas y el
  validador en el ciclo) contra la tarjeta de una sola vuelta (Spark Open con los mismos datos, sin
  herramientas; las dos con el rescate de Spark 1.3). Un juez ciego (Muse Spark 1.3) recibe lo que se
  ve y se dice en el arranque y las dos tarjetas como «1» y «2», sin saber cuál es cuál, y elige cuál le
  sirve más a quien edita. Cada par se juzga en los dos órdenes; solo cuenta si elige la misma las dos
  veces (`eval/juez_tarjetas.py`).
- **Regla.** Si el agente gana al menos 60 % de los pares con veredicto firme y hay al menos 20 pares
  firmes, decimos que las herramientas mejoran la tarjeta, con la cifra. Si no, no lo decimos y
  reportamos el resultado tal cual.
- **Límite.** El juez es un modelo, no un editor: mide qué tarjeta parece más útil y mejor apoyada en
  los datos, no si retiene más gente.
- **Resultado (misma noche).** 50 casos juzgados en los dos órdenes; 39 con veredicto firme. El juez
  prefirió la tarjeta de una sola vuelta en 27 y la del agente en 12 (31 %); en 11 cambió de opinión
  al cambiar el orden. La regla no se cumple: **no decimos que las herramientas mejoren la tarjeta.**
  Límite a la vista: el juez solo recibe los datos que tuvo la tarjeta de una vuelta, así que lo que el
  agente sacó de SAM o de videos parecidos puede parecerle inventado. El agente sigue por omisión por lo
  que sí está medido (cierra solo los 50 casos y corrige lo que el validador le regresa), y la revisión
  humana de las tarjetas queda pendiente. Costo: USD 0.80.

## 29-oct-2026 · ¿Retina sirve con un creador que nunca vio? Regla escrita antes de medir

- **Por qué.** Retina es para cualquier persona, no solo para Badabun. Hoy el nivel usa el talento,
  el tipo de producción (prefijo del código) y el nombre del archivo de Badabun; con un video de fuera
  todo eso viene vacío y el número queda en el promedio de su duración.
- **Qué se mide** (`eval/cualquier_video.py`). Prueba de jul-sep 2026, solo videos con talento. Los
  talentos se reparten en 5 grupos y cada grupo se esconde por completo (entrenamiento e historia de
  videos parecidos) antes de predecir sus videos, que entran sin talento, sin código y solo con su
  título: así llega un video de fuera. Se comparan:
  A. promedio de videos de su duración (90 días);
  B. Retina de hoy con esos campos vacíos;
  C. cerebro para cualquier video: duración, si es reel, hora y día, palabras del título publicado y
     la voz del arranque (cuándo empieza a hablar, cuánto se dice en 3 y 15 s, pausas, preguntas,
     primeras palabras). Nada propio de Badabun.
  Aparte, en talentos conocidos (prueba normal): v0 de hoy contra C más la capa de la casa (talento y
  tipo), para ver que lo de Badabun suma encima.
- **Regla.** C pasa a ser el cerebro base si, contra B, baja el error de toda la curva y sube la
  correlación de orden a los 15 s (spearman), y en al menos una de las dos los intervalos de 95 % no
  se cruzan. Además, C más la casa no puede quedar peor que la v0 en talentos conocidos (intervalos
  cruzados cuentan como empate). Si C no pasa, B se queda y la tarjeta avisa cuando el video está lejos
  de lo que Retina conoce.
- **Límite.** Todo esto es Facebook y el público de Badabun. Esconder un talento de Badabun no es lo
  mismo que un creador de YouTube con su propio público; es lo más cercano que permite la data.
- **Resultado (29-oct, jul-sep, videos de talentos escondidos).** C gana en las cinco medidas
  (error a los 3 s, a los 15 s, a la mitad, al final y en toda la curva) y en el orden a los 15 s, pero
  los intervalos sueltos se cruzan en las dos medidas de la regla: **por la regla escrita, C no pasa.**
  En talentos conocidos, C más la casa no supera a la v0 (intervalos cruzados): la v0 se queda para los
  videos de la casa. Cifras en la carpeta de datos privada, como todas las de la base de Badabun.
- **Confirmación (regla escrita antes de correrla).** Los intervalos sueltos castigan de más cuando
  los dos cerebros se miden en los mismos videos; lo justo es la diferencia por video (B menos C) con
  su intervalo. Como esa idea salió después de ver jul-sep, jul-sep queda como pista y la decisión se
  toma en un periodo que C no ha visto: prueba ene-jun 2026, entrenamiento antes de 2026-01-01, C sin
  cambios (mismos rasgos, λ elegida igual). C pasa si el intervalo de 95 % de la diferencia pareja del
  error de toda la curva queda entero arriba de 0 y la diferencia pareja del orden a los 15 s es
  positiva. Si pasa, Retina usa C para videos de fuera y la v0 para los de la casa. Si no, B se queda
  y la tarjeta avisa cuando el video está lejos de lo que Retina conoce.
- **Resultado de la confirmación (29-oct, ene-jun 2026, videos de talentos escondidos).** C pasa:
  el intervalo de 95 % de la diferencia pareja del error de toda la curva queda entero arriba de 0 y
  la diferencia pareja del orden a los 15 s es positiva, también con su intervalo arriba de 0. Lo mismo
  sale en jul-sep con la comparación pareja. La mejora es real y chica: C se acerca más que B en un
  poco más de la mitad de los videos y recorre cerca de la mitad del camino entre no conocer al creador
  y conocerlo. **Se decide:** Retina usa C para un video de fuera cuando ya tiene su voz (Voice
  Transcribe), la v0 para los de la casa (talento o tipo de producción conocidos) y, sin voz, la v0 con
  los campos vacíos. La tarjeta dice cuando no conoce al creador. Cifras en la carpeta privada.

## 29-oct-2026 (noche) · El cerebro público. Regla escrita antes de medir

- **Por qué.** Quien clone el repo debe poder revisar su propio video sin los datos de Badabun. Lo que se
  publica es lo aprendido de la retención, nunca un video: sin ingresos, y sin aprender de videos
  no elegibles, de temas fuera de alcance o graves (`reglas/alcance-v1.json`, en título y primeras palabras
  dichas; ante la duda, fuera) ni de nombres de talentos. Va en un JSON (`retina.publico`), no en pickle.
- **Qué se mide.** En `eval/cualquier_video.py`, la variante D arma el cerebro público con lo de antes
  del corte y sin el grupo escondido, y usa la curva fija por duración que trae el archivo (la de los
  90 días antes del corte), como pasará con quien lo use.
- **Regla.** D se publica si en ene-jun 2026, con talentos escondidos, la diferencia pareja del error de
  toda la curva contra la curva fija por duración (lo único que quedaría sin él) tiene su intervalo de
  95 % entero arriba de 0. Se reporta además cuánto pierde contra B y C. Si no pasa, el archivo público
  lleva solo las curvas por duración y la tarjeta lo dice.
- **Resultado (29-oct, ene-jun 2026, videos de talentos escondidos).** D pasa: la diferencia pareja
  del error de toda la curva contra la curva fija por duración tiene su intervalo de 95 % entero arriba de
  0, y también ordena mejor los videos a los 15 s. Contra B (la v0 de la casa con los campos vacíos) queda
  empatado, sin llevar nada de la casa. Contra C pierde un poco: una parte por la curva fija (la de los 90
  días antes del corte, no la que se mueve día a día) y otra por lo que se dejó fuera. **Se decide:** el
  repo lleva `modelos/retina-publico.json` en cuanto haya autorización para publicar lo aprendido (decisión 2);
  hasta entonces sigue fuera por `.gitignore`. Cifras en la carpeta privada.

## 29-oct-2026 (noche) · Lo que ve el jurado: idioma, SAM, Muse Image y el plan B

- **Idioma.** El jurado lee inglés: el panel manda su idioma al subir el video y Spark describe, escribe la
  tarjeta y la comparación A/B en ese idioma (explicar-v7, comparar-v2). Las reglas de Meta traen su título
  en inglés. Probado de punta a punta en inglés: la tarjeta pasó el validador al primer intento.
- **SAM sin agente.** En el modo público la tarjeta sale de una vuelta (el juez ciego del 28-oct la prefirió),
  y SAM solo corría dentro del agente. Ahora, antes de la tarjeta, Muse Spark 1.3 elige de la lista cerrada
  qué promete el título (nunca personas) y SAM revisa si se ve en los primeros 3 segundos. Cuesta menos de
  un centavo.
- **Muse Image a pedido.** En la app, un botón dibuja el storyboard del cambio (unos USD 0.03). No corre solo:
  cuesta, y así lo aprueba quien lo aprieta.
- **Plan B de la ridge.** Si los organizadores dicen que los pesos fijos cuentan como modelo que no es de
  Meta, `RETINA_SOLO_MODELOS_META=1` los apaga: el número queda en el promedio de su duración, no hay nivel
  de riesgo y la tarjeta lo dice. Probado de punta a punta con un video. Mientras no contesten, sigue apagado.


## 29-oct-2026 (noche) · ¿Un mejor inicio trae más alcance en Facebook? Regla escrita antes de medir

- **Por qué.** Retina promete revisar el inicio. Eso vale si un inicio que retiene más se traduce en lo que
  le importa a una página: alcance y que Facebook lo recomiende. Si no, la curva sería un dato bonito.
- **Datos.** La base de curvas más las demás métricas de los exports de Meta (`retina.metricas_meta`), por
  publicación. Fuera: videos no elegibles o sin dato de elegibilidad, y sin alcance. Ninguna columna de ingresos se
  lee.
- **Qué se mide** (`eval/alcance_privado.py`).
  - Inicio: cuánto retiene el video al terminar su primer cuarto (punto 10 de 41) contra sus parecidos
    (la regla de siempre, solo con videos anteriores).
  - Alcance relativo: su alcance contra la mediana de los videos de su misma duración de los 90 días
    anteriores (en logaritmo).
  - Recomendación: la parte de los segundos vistos que vino de Recomendaciones.
- **Regla 1 (inicio y alcance).** Decimos que un mejor inicio va con más alcance si la correlación de orden
  (spearman) entre las dos cosas es positiva con su intervalo de 95 % entero arriba de 0 en 2020-2023 y
  también en 2024-2026, por separado. Para decirlo en palabras: el alcance mediano del tercio de videos con
  mejor inicio contra el del tercio con peor, con su intervalo. Revisión aparte: lo mismo quitando el
  efecto de cada talento (cada video contra el promedio de su talento). Es una relación, no prueba causa.
- **Regla 2 (lo que Retina predice antes de publicar).** Con el modelo entrenado antes del 1-jul-2026, en
  jul-sep 2026: si la correlación entre el inicio que predijo Retina y el alcance relativo real tiene su
  intervalo de 95 % arriba de 0, decimos que la predicción de Retina sirve para anticipar alcance.
- **Límite conocido.** Un video que Facebook reparte a gente que no lo buscaba suele retener menos; eso
  empuja la correlación hacia abajo. Si aun así sale positiva, es evidencia conservadora.
- **Resultado (29-oct, noche).** Pasan las dos reglas. Regla 1: en 2020-2023 y en 2024-2026, por separado,
  la correlación entre el inicio y el alcance relativo es positiva con el intervalo entero arriba de 0, y
  el tercio con mejor inicio llegó a varias veces más gente que el tercio con peor. Se sostiene quitando el
  efecto de cada talento, y el inicio también va con una parte mayor de reproducciones por
  Recomendaciones. Regla 2: en jul-sep 2026, lo que Retina predijo antes de publicar se relaciona con el
  alcance real (intervalo arriba de 0): el tercio que Retina calificó mejor llegó a más gente que el que
  calificó peor. Es una relación, no prueba causa. Cifras en la carpeta privada.

## 29-oct-2026 (noche) · Corrección: los créditos sí pueden entrenar con lo que se manda

Una entrada anterior decía que lo que se manda con los créditos del concurso no se usa para entrenar.
En el Discord del concurso (27-oct, 14:43), una persona de Meta escribió lo contrario: con los créditos gratis,
el contenido que se manda puede usarse. Quien corra Retina con contenido de una empresa debe saberlo; por eso existe
el candado de `RETINA_SOLO_PUBLICADOS` (apagado por omisión, para revisar antes de publicar).

