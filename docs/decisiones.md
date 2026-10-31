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
  prueba en cada una. Va a la explicación de Spark, que sí la lee.

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
- **Qué salió en los 50 casos** (`eval/revision_meta_casos.py`): los videos de la empresa ya cumplen casi
  todo (casi todos abren con gancho y mensaje y casi todos se entienden sin sonido). Lo único que separa
  es si lo prometido se ve en los primeros 3 s, y con tan pocos casos medidos la diferencia no es clara.
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


## 29-oct-2026 (noche) · ¿El semáforo sirve con videos de fuera? Regla sellada antes de medir

- **Por qué.** La auditoría del 29-oct encontró que el semáforo del cerebro público pone en «alto» a
  demasiados videos de fuera: sus cortes se fijaron con otra referencia (la de 90 días y el tipo de
  producción), y el modo público usa la curva fija por duración.
- **Qué se mide** (`eval/semaforo_publico.py`). Dos pruebas en periodos que el semáforo no ha visto:
  entrenando antes del 1-jul-2025 y probando jul-dic 2025; entrenando antes del 1-ene-2026 y probando
  ene-jun 2026. El cerebro público se arma solo con lo de antes del corte. Los cortes de «alto» y «medio»
  se recalculan por duración con los videos de los 180 días antes del corte, como pasaría al usarlo (40 % y
  75 % de lo que predice). Los videos de prueba entran como de fuera (sin talento ni código), elegibles.
  «Perdió de más» = su gancho y primer cuarto perdieron más gente que la curva de su duración, la misma
  que ve la persona en la tarjeta.
- **Regla.** El semáforo se queda en el modo público solo si, en las dos pruebas: (1) «alto» sale en
  entre 15 % y 35 % de los videos; (2) entre los «alto», la parte que de verdad perdió de más le gana a la
  tasa base del periodo con intervalos de Wilson al 95 % que no se tocan; y (3) entre los «bajo», esa parte
  queda por debajo de la tasa base. Si no pasa, el modo público no muestra semáforo: la tarjeta dice lo
  que vio y el número queda como referencia. Una duración con menos de 50 videos de prueba se reporta
  como «no medida» y la tarjeta avisa que Retina no conoce ese formato.
- **Resultado (29-oct, noche; corrida con el commit acf17d2, el de la regla).** El semáforo sí distingue: en
  las dos pruebas, los videos en «alto» perdieron de más bastante más seguido que la tasa base, con
  intervalos que no se tocan, y los «bajo» quedaron por debajo. Pero en la primera prueba (jul-dic 2025)
  salieron en «alto» demasiados videos, más del 35 % que pone la regla. **Por la regla sellada, el modo
  público no muestra semáforo.** La tarjeta dice lo que vio, el número queda como referencia (ese sí pasó
  su medición) y, en videos de menos de 30 segundos, avisa que Retina vio pocos así. No se cambia la regla
  después de ver el resultado. Cifras en la carpeta privada.

## 29-oct-2026 (noche) · ¿Leer el inicio mejora el número? Regla sellada antes de medir

- **Por qué.** La auditoría encontró que el número sale sobre todo del título y la duración, no de cómo arranca
  el video. Lo que mejor funciona en la literatura reciente (SnapUGC 2025, anuncios 2026) es que un modelo
  multimodal llene una ficha fija del inicio y un modelo pequeño aprenda de ella.
- **Qué se mide.** La ficha del arranque (`retina.ficha`): Muse Spark Open lee el título y las primeras 60
  palabras dichas y anota el tipo de gancho, si quien habla se presenta antes del tema, si el tema llega en la
  primera frase, si promete algo que se verá, si hay cifra o se pide interacción, claridad, curiosidad y
  emoción. En `eval/cualquier_video.py` (variante E), el cerebro público más la ficha contra el cerebro público
  solo (D), en los mismos videos de talentos escondidos, en dos periodos: ene-jun 2026 (entrenando antes del
  1-ene-2026) y jul-dic 2025 (entrenando antes del 1-jul-2025). Fichas desde 2022; donde no hay, ceros.
- **Regla.** La ficha entra al número si, en los dos periodos, la diferencia pareja del error de toda la curva
  (D menos E) tiene su intervalo de 95 % entero arriba de 0 y la diferencia pareja del orden a los 15 s (E
  menos D) es positiva. Si entra, Retina le pide la ficha de cada video nuevo a Muse Spark Open al revisarlo.
  Si no, la ficha se queda solo como descripción en la tarjeta (la táctica del gancho), sin tocar el número.

- **Resultado (29-oct, noche; corrida con el commit 8fcfaac, el de la regla).** Pasa en los dos periodos: con
  la ficha, el número se equivoca menos con creadores que nunca vio (diferencia pareja con intervalo entero
  arriba de 0) y ordena mejor los videos a los 15 s. **Se decide:** la ficha entra al cerebro público
  (`modelos/retina-publico.json`, `rasgos.ficha`) y Retina se la pide a Muse Spark Open a cada video nuevo.
  **Cómo se anotó, exactamente:** la base de fichas con la que se midió se anotó sin temperatura fija y en
  lotes de 20 videos por llamada. La temperatura 0 (para que el mismo video dé la misma ficha) entró después,
  y la app pide un video a la vez. La ficha que corre en la app no es idéntica a la que se midió, y esa
  diferencia no se ha medido. Cifras en la carpeta privada.
- **Lo que pasó con cada táctica** (`eval/tacticas_gancho.py`, descriptivo, elegibles). En la tarjeta solo van,
  en palabras y sin cifras, los rasgos cuya diferencia contra videos parecidos tuvo un intervalo de 95 % lejos
  de cero: presentarse antes del tema, saludo o presentación como gancho, decir el tema tarde, poca curiosidad,
  arrancar con pura alegría o ternura (retuvieron menos); un dato o una cifra, un conflicto, mucha curiosidad,
  sorpresa o indignación (retuvieron más). Describe lo que pasó con otros videos, no promete nada del tuyo.

## 29-oct-2026 (noche) · Semáforo público v2. Regla sellada antes de medir

- **Por qué.** La v1 no pasó su regla y no se reajusta. La v2 es otra hipótesis: el nivel sale del número que sí
  pasó su medición (el cerebro público con la ficha del arranque): cuánta gente predice que se va de más en el
  gancho y el primer cuarto, contra la curva fija de su duración.
- **Qué se mide** (`eval/semaforo_publico_v2.py`). La misma vara que la v1: dos periodos que no ha visto
  (jul-dic 2025 y ene-jun 2026, con el cerebro armado solo con lo de antes), cortes por duración con los 180 días
  antes del corte (40 % y 75 %), videos de prueba como de fuera y elegibles, y «perdió de más» contra la curva fija.
- **Regla.** La misma de la v1: en las dos pruebas, «alto» en entre 15 % y 35 % de los videos; la parte de los
  «alto» que de verdad perdió de más le gana a la tasa base con intervalos de Wilson que no se tocan; y los
  «bajo» quedan debajo de la base. Si pasa, el modo público vuelve a mostrar semáforo, con estos cortes por
  duración. Si no, se queda sin semáforo.
- **Resultado (29-oct, noche; corrida con el commit d809422, el de la regla).** Pasa en las dos pruebas: «alto»
  sale en entre 15 % y 35 % de los videos, los «alto» perdieron de más bastante más seguido que la tasa base con
  intervalos que no se tocan, y los «bajo» quedaron debajo. **Se decide:** el modo público vuelve a mostrar
  semáforo con la v2. Las duraciones sin videos suficientes para calibrar (menos de 30 s y más de 4 min) quedan sin
  semáforo y con el aviso de formato poco conocido. Cifras en la carpeta privada.

## 29-oct-2026 (noche) · El semáforo v2 no entra al modo público: se trata como exploratorio

- **Por qué.** La auditoría del 29-oct en la noche encontró que la v2 pasó su regla, pero no es una prueba limpia:
  se escribió después de ver fallar la v1, en los mismos dos periodos (jul-dic 2025 y ene-jun 2026), que ya se habían
  usado varias veces para decidir otras cosas (la ficha, el cerebro público). Cada decisión se tomó viendo la anterior.
  La v1 falló por marcar demasiados «alto», no por distinguir peor, y la v2 corrige justo eso. Además, en jul-dic 2025
  sale al revés en videos de 2 a 4 minutos y no distingue en los de 30 a 60 segundos: lo carga la duración de 1 a 2
  minutos. Por la regla de la casa («lo que no pase no entra, y no se reajusta después de ver el resultado»), un
  reajuste no cuenta como pasar.
- **Se decide.** El modo público sigue sin semáforo: la tarjeta dice lo que vio y el número queda como referencia. El
  resultado de la v2 se queda publicado aquí como exploratorio. Esos dos periodos ya no se usan para ninguna prueba
  nueva.
- **Cómo podría entrar.** Solo con una prueba hacia adelante, en videos que todavía no existen al escribir esta regla:
  los que la página publique del 30-oct al 2-nov de 2026 (hora de México), elegibles, sin fuera de alcance ni temas fuera de alcance, como
  de fuera (sin talento ni código). Para cada uno, Retina anota con el cerebro público (con voz y ficha) la curva y el
  nivel de la v2 antes de bajar su retención, y la huella sha256 de ese archivo se publica antes de leer cualquier
  retención. Pasa el número si la diferencia pareja del error de toda la curva (curva fija por duración menos cerebro
  público, en puntos) tiene su intervalo de 95 % entero arriba de 0. Pasa el semáforo con la misma vara de la v1: «alto» entre 15 %
  y 35 %, los «alto» pierden de más con intervalos de Wilson que no se tocan con la tasa base, y los «bajo» quedan
  debajo de la base. Con menos de 100 videos que se puedan medir no se concluye nada y el semáforo sigue fuera.

## 30-oct-2026 · Retina deja de calificar y entrega la apertura arreglada y comprobada. Regla escrita antes de medir

- **Por qué.** La regla del concurso dice que todo modelo que el proyecto llama al correr debe ser de Meta, y su personal
  separa «modelo entrenado» (no se vale) de «código determinista» (sí se vale). La fórmula aprendió sus pesos de datos y
  su aporte es mínimo (unas 2 personas de cada 1,000), así que de fábrica queda apagada, contesten lo que contesten.
  Sin ella, «Spark describe y aconseja» queda cerca de los «simple image analyzers». El centro de Retina cambia a producir
  y comprobar: Muse Spark Open reescribe el arranque, Muse Image lo dibuja, y reglas fijas de código más SAM 3.1 lo
  comprueban. Si algo falla, Spark Open lo corrige con la lista exacta de lo que falló, hasta 2 veces. Nada que no pase
  llega a la persona. El título nunca se toca.
- **Qué se mide.** Los 50 casos de siempre (`eval/apertura_casos.py`), sin datos de retención. Antes de ver un solo
  resultado, Muse Spark 1.3 eligió de la lista cerrada de SAM lo que promete cada título: 18 casos prometen algo que se
  ve y 32 no. La lista quedó fija (sha256 de la lista privada: 981da79b9045e5cc95d4aec402afdeb65133b8dd2ed02ead03bf2557741df85e).
- **Regla.** Las tres tienen que pasar:
  - A. De los 18 con promesa visible, al menos 15 (80 %) pasan todo en 2 correcciones o menos: las reglas de texto (sin
    anzuelos, sin tocar intocables, sin cifras ni nombres que no salgan del video, el tema del título en la primera
    frase, largo de 10 a 15 segundos), el filtro de integridad en cada cuadro, y SAM 3.1 encuentra el objeto en el primer
    cuadro.
  - B. De los 32 sin promesa visible, al menos 26 (80 %) pasan lo mismo menos SAM, que ahí no aplica.
  - C. Prueba trampa: 10 cuadros aprobados contra el objeto de otro caso, que el cuadro no tiene. SAM rechaza al menos 9.
    Así se demuestra que el revisor no aprueba todo.
- **Se reporta, sin ser condición.** En cuántos de los 18 el borrador no mostraba la promesa en sus primeros 3 segundos
  (SAM sobre el video real) y la apertura nueva sí; el costo; y el intervalo de Wilson de 95 % de A. Con 18 casos el
  intervalo es ancho y se dice.
- **Lo que esto no mide.** Si la apertura nueva retiene más gente. Eso nunca se midió y Retina no lo promete. El
  «después» es un boceto (voz y dibujos), no un video grabado.
- **Cómo se afina.** Las instrucciones y el validador se afinan solo con 9 revisiones que no están entre los 50. Antes de
  correr, el código se congela en un commit cuyo hash va en la bitácora. Si A, B o C fallan, el resultado se publica
  igual y no se reajusta en estos 50 casos.
- **Resultado (30-oct; corrida con el commit 598b4bb, el del código congelado).** **No pasó.** A: 10 de 18, y pedía 15
  (intervalo de 95 %: de 34 % a 75 %). B: 31 de 32, y pedía 26. C: SAM rechazó 10 de 10. En 9 de los 18 el borrador no
  mostraba la promesa en sus primeros 3 segundos, y la apertura nueva sí la mostró en 2 de esos 9. De las 41 aperturas
  aprobadas, 37 pasaron a la primera y 4 con una corrección. Costo: USD 3.36. Estos 50 casos ya no se usan para esto.
- **Por qué falló A.** En 8 de los 18 casos la voz y las reglas pasaron y lo que falló, las tres veces, fue SAM. Un
  diagnóstico con escenas inventadas (`eval/sam_objetos_dificiles.py`, sin ningún caso de la medición) encontró que casi
  siempre era la palabra y no el dibujo: SAM no reconoce «tortilla» ni «nopal», pero en esos mismos dibujos encuentra
  «food» y «cactus». «Fair», «city» y «dump» son escenas, no objetos, y Muse Image rechaza dibujar «vape».

## 30-oct-2026 · Los organizadores contestaron sobre la fórmula, y sigue apagada

- **Qué dijeron (Discord, 30-oct, 12:12 y 12:14, hora de Tijuana).** Una fórmula ridge fija, ajustada fuera de línea con datos
  propios, entra en lo que aceptan como componente pequeño entrenado por uno mismo. Es «borderline»: vale si el repo documenta
  todo el método de entrenamiento, la descripción de los datos y los pesos fijos, si el README dice qué hace esa capa, y si los
  modelos de Meta hacen claramente el trabajo de fondo. Apagarla de fábrica es la opción sin riesgo.
- **Se decide.** Sigue apagada de fábrica. Prenderla obligaría a publicar pesos y datos de Badabun a cambio de muy poco
  (unas 2 personas de cada 1,000), y lo que Retina entrega ahora ya no depende de ese número.

## 30-oct-2026 · El número no sirve para comparar el arranque viejo con el nuevo (exploratorio)

- **Qué se probó.** En las 41 aperturas aprobadas de la medición, el número con el arranque original contra el número con el
  arranque reescrito, a los 15 segundos. Sin retención real y sin regla previa: era una exploración.
- **Qué salió.** Bajó en 27, subió en 7 y casi no cambió en 7. En promedio bajó 1 persona de cada 100.
- **Se decide.** Retina no muestra un número «después». No se sabe si la baja es real o un efecto de cómo se arma la voz nueva,
  y la fórmula aprendió de diferencias entre videos distintos, no entre dos versiones del mismo video. Ajustarla hasta que suba
  sería acomodar el resultado. Esto tampoco demuestra que la apertura nueva sea peor: retención real no se midió.

## 30-oct-2026 · Segunda medición de la apertura, con videos nuevos. Regla escrita antes de medir

- **Por qué.** La primera medición no pasó (10 de 18) y esos 50 casos ya no sirven: un arreglo probado en los mismos casos
  no demuestra nada. Esta usa videos que no se han tocado.
- **Qué cambió desde la primera.** El vocabulario de SAM, calibrado con dibujos inventados (`eval/calibrar_vocabulario.py`,
  `reglas/sam-vocabulario-v1.json`): de 167 palabras, SAM encontró 104 tal cual, 10 con su palabra general («tortilla» se busca
  como «food») y 53 salen de lo que se puede comprobar con SAM. También las correcciones de la revisión independiente (un dibujo
  rechazado gasta un intento, los cuadros no pueden nombrar a nadie que no salga del video). Las instrucciones de escritura no
  cambiaron.
- **Lo que este cambio hace a la medición.** Quitar las palabras difíciles ayuda a pasar, y eso no se esconde: esas 53 palabras
  ya no se comprueban con SAM. Por eso se reporta también qué parte de los títulos queda con comprobación.
- **Qué se mide.** 30 videos de jul-sep de 2026 que no están en los 50 ni en la afinación, barajados con la semilla 20261030. Son
  los primeros 30 cuyo título promete algo que SAM puede comprobar, de 83 títulos revisados. La lista quedó fija antes de ver
  un resultado (sha256 de la lista privada: d2b86e5f53adad56453dc887b7324fd9f9b203bde29367dccc2f8b8bf56139e7). Sin retención y sin
  video: el título y lo que se dice (`eval/apertura_nuevos.py`), porque lo que falló fue el dibujo y SAM, no la lectura del video.
- **Regla.** Las dos tienen que pasar:
  - A. Al menos 24 de 30 (80 %) pasan todo en 2 correcciones o menos: las reglas de texto, el filtro en cada cuadro y SAM encuentra
    lo prometido en el primer cuadro.
  - B. Prueba trampa: 10 cuadros aprobados contra un objeto de otra familia. SAM rechaza al menos 9.
- **Se reporta, sin ser condición.** El intervalo de Wilson de 95 % de A, qué se corrigió, qué falló y el costo.
- **Si no pasa.** Se publica igual, junto con la primera, y no se reajusta en estos 30 casos. Lo que esto no mide es lo mismo que
  antes: si la apertura nueva retiene más gente.

- **Resultado (30-oct; corrida con el commit d44e721, el del código congelado).** **Pasó.** A: 29 de 30, y pedía 24 (intervalo de
  95 %: de 83 % a 99 %). B: SAM rechazó 9 de 10, justo lo que pedía. El cuadro que no rechazó era un perro frente a una casa con la
  calle de fondo y se le preguntó por «building»: sí había edificios, así que la trampa estaba mal puesta, pero la cuenta se queda
  como salió. De las 29, 23 pasaron a la primera y 6 con una corrección. La que no pasó fue por SAM. Costo: USD 1.84.
- **Cómo leerlo.** Con el vocabulario calibrado, 30 de 83 títulos prometen algo que SAM puede comprobar; en los demás solo aplican las
  reglas de texto y los cuadros. Esta medición usa título y voz, sin video. Mide que la apertura pase las comprobaciones, no que
  retenga más gente. La primera medición no pasó y se queda publicada.

## 30-oct-2026 · El número regresa, con la respuesta completa de los organizadores

- **Por qué se cambia.** Jossafat vio la tarjeta sin número y dijo que predecir la retención es lo importante y lo llamativo.
  Tiene razón: la decisión anterior miró solo cuánto mejora el acierto, no lo que el número hace por el producto. Esta entrada
  sustituye a «Se decide» de la entrada anterior sobre la fórmula.
- **Qué contestaron en office hours (30-oct, 13:14, hora de Tijuana).** Los coeficientes ridge se aceptan si el README explica qué
  hace la capa, con los detalles del ajuste y los pesos fijos en el repo. Una tabla de promedios por duración es código determinista
  y se vale. Apagarla sigue siendo lo más seguro. Sobre la categoría: «simple image analyzers» está en la lista, y las ideas cercanas
  se valen si el centro es una versión nueva y no genérica, así que hay que abrir el README y la demo con lo que hace distinto al
  proyecto.
- **Se decide.** El número vuelve prendido de fábrica, documentado en `docs/numero.md`, y el README abre con lo que hace distinta a
  Retina. Publicar `modelos/retina-publico.json` depende de la empresa. Sin ese archivo Retina corre sin número.
- **Lo que no cambia.** No hay número para la apertura nueva, el semáforo sigue fuera y Retina no promete retener más gente.

## 30-oct-2026 · Lo que corrigió la auditoría estricta

Cinco revisiones independientes rechazaron la entrega como estaba. Las entradas anteriores se quedan como se escribieron, porque varias
están selladas; lo que estaba mal se corrige aquí.

- **Erratas de entradas anteriores.**
  - «Unas 2 personas de cada 1,000» era solo lo que aporta la ficha (2.0 y 1.4). La fórmula completa contra la curva fija gana de 5 a 8
    de cada 1,000 en toda la curva.
  - «Unos 30 mil videos» son 23,710 de 32,906: lo demás queda fuera por elegibilidad o temas. De los
    que entraron, 9,003 no tienen ficha y 974 no tienen voz.
  - λ = 300 no se eligió con 10 grupos de creadores escondidos: se eligió con el último 20 % por fecha, en la variante C, no elegibles y
    sin ficha, y no se volvió a elegir para el archivo publicado.
  - «3.5 veces» es el mejor tercio contra el peor en retención real. Con lo predicho fue 1.49 veces (intervalo de 95 %: 1.19 a 1.98), con
    el modelo de la casa; el público no se midió. «Predicho antes de publicar» fue una corrida del 29-oct sobre videos ya publicados.
  - La segunda medición de la apertura es una regresión, no una validación, por lo que dice `docs/results.md`.
  - En el «10 de 10» de la primera trampa, 3 usaron palabras que SAM casi no reconoce: informa 7 de 7.
- **La curva cuenta desde los 3 segundos.** Marca casi 100 hasta unos 3 s en todas las duraciones y cae justo después: en 2,953 videos de
  un minuto, 99.8 a los 2.9 s y 79.8 a los 4.4 s. La forma está medida y la causa es nuestra lectura. El panel dice «de cada 100 que pasan
  los primeros 3 segundos», ya no enseña el cuadro de los 3 segundos y avisa que no ve a quien se va antes.
- **El margen se midió y se enseña** (`eval/margen_numero.py`). Con creadores escondidos falla por 8.9 de cada 100, y por 10.2 si además se
  entrena solo con lo anterior a 2026; la curva fija falla por 10.4 y 11.7. El panel dice «más o menos 11». Una diferencia menor que el
  margen se muestra como «parecido», y eso pasa en unos 9 de cada 10 videos. La auditoría había estimado 7.6; esta cuenta sustituye a esa.
- **La prueba hacia adelante del 3-nov no se corre.** La regla pide 100 videos y en 4 días salen 52 de mediana y 67 como máximo, antes de
  filtros: por su propia regla no concluye nada. El semáforo sigue fuera y nadie tiene que juntar esos datos. No se había leído ninguna
  retención de esos videos.
- **Normas de Facebook.** No tienen regla ni medición, y ahora se dice. Lee lo que Spark describió y lo que se transcribió, no el archivo
  de video. Una cita ya tiene que estar en ese segundo y en los valores, no en los nombres de los campos.
- **Comparar dos versiones.** Es la lectura de Spark sobre dos arranques, no una predicción de cuál pierde menos gente: en eso Spark no le
  ganó a una moneda.

## 30-oct-2026 · Tercera medición: apertura-v2 en videos nuevos. Regla escrita antes de medir

- **Por qué.** La segunda medición es una regresión, no una validación: se quitaron las palabras que SAM no reconocía y el código le
  ordenaba a Muse Image poner al centro lo que SAM iba a buscar, así que pasar era lo esperado. Además la regla 3 («trae la promesa al
  inicio») vaciaba el video: un ejemplo soltaba los tres trucos en 14 de 96 segundos. Y nadie había juzgado si las aperturas son fieles.
- **Qué cambió (apertura-v2).** La regla 3 pide cumplir la promesa con su primera prueba y dejar lo demás al video. El código ya no le
  ordena nada a Muse Image: quien escribe recibe el objeto prometido y el cuadro se dibuja solo de lo que escribió, así que SAM comprueba
  la escritura. Las reglas de código son las mismas, más cifras con letra que faltaban y gentilicios que no son nombres.
- **Cómo se afinó.** Con 6 casos aparte (`--piloto`, semilla 20261032), corridos dos veces, que no entran a esta medición. Sirvieron para
  quitar dos defectos de redacción: mezclar inglés y español en los cuadros, y anunciar «la primera prueba es».
- **Qué se mide** (`eval/apertura_v2.py`, `eval/juez_aperturas.py`). Videos de jul-sep de 2026 de hasta 4 minutos que no están en los 50, los
  30, la afinación ni el piloto, barajados con la semilla 20261031: los primeros 30 cuyo título promete algo que SAM puede comprobar y los
  primeros 20 que no, de 93 títulos revisados. Sin retención y sin video: el título y lo que se dice. La lista quedó fija antes de ver un
  resultado (sha256 de la lista privada: 3adbcb88378cfc0a476c9f49355b41a3c696938be0b846c6f60999132a100314).
- **Regla.** Todas tienen que pasar:
  - A. Al menos 24 de los 30 con promesa pasan todo en 2 correcciones o menos, y SAM encuentra lo prometido en el primer cuadro.
  - B. Al menos 16 de los 20 sin promesa pasan lo mismo menos SAM, que ahí no aplica.
  - C. Trampa lejana: 10 cuadros aprobados contra un objeto de otra familia, de los que SAM encuentra tal cual. SAM rechaza al menos 9.
  - D. Juez ciego, Muse Spark 1.3, con todo lo que se dice en el video: al menos 80 % de las aprobadas son fieles.
  - E. El mismo juez: al menos 80 % de las aprobadas dejan algo importante para el resto del video.
  - F. El mismo juez compara, sin saber cuál es cuál y en los dos órdenes, cada apertura con lo que el video dice en sus primeros 15
    segundos. La nueva gana al menos 60 % de los pares firmes decididos, con al menos 20 decididos.
- **Se reporta, sin ser condición.** Los intervalos de Wilson, que tratan como independientes casos que no lo son (11 de 30 son perro, gato
  o cachorro); la trampa cercana, 10 cuadros contra otro objeto de su familia, donde el revisor es más débil; correcciones, fallas y
  costo; y, como referencia, D y E sobre las 29 aperturas de la versión anterior, sin volver a escribirlas.
- **Lo que esto no mide.** Si la apertura nueva retiene más gente. El juez es un modelo, no una persona ni una audiencia. No hay video.
- **Si no pasa.** Se publica igual y no se reajusta en estos casos. Estos 50 casos no se vuelven a usar para esto.

## 30-oct-2026 · Resultado de la tercera medición

Va en una entrada aparte para que la huella de la regla no cambie. Corrida con el commit c439813, el de la regla, desde una copia congelada.

- **Pasó las seis, a la primera.** A: 29 de 30, pedía 24 (intervalo de 95 %: de 83 % a 99 %). B: 17 de 20, pedía 16 (de 64 % a 95 %). C: SAM rechazó 10
  de 10. D: 45 de 46 fieles, pedía 80 %. E: 45 de 46 dejan algo para el resto, pedía 80 %. F: la nueva ganó 37 de 42 pares firmes (88 %), pedía 60 % con
  al menos 20; 4 pares cambiaron con el orden.
- **Se reporta.** Trampa cercana: 10 de 10. De las 46 aprobadas, 41 a la primera, 3 con una corrección y 2 con dos. Las 4 que no pasaron: SAM no encontró
  la promesa, los cuadros no se pudieron dibujar, un nombre y un anzuelo. Costo de escribir, dibujar y comprobar: USD 3.00. Referencia sobre las 29 aperturas de
  la versión anterior: 29 fieles y 26 que dejan algo.
- **Cómo leerlo.** El juez es un modelo. F favorece a la nueva porque compara texto limpio contra voz transcrita. 45 de 46 contra 26 de 29 son videos
  distintos y sus intervalos se tocan: es indicio, no prueba, de que apertura-v2 ya no vacía el video. 15 de los 30 con promesa son mascotas o animales. Sin
  video. Retención, no medida. Estos 50 casos ya no se usan para esto.

## 30-oct-2026 · Lo que salió de usar Retina con videos reales

- **Traducción.** El botón de idioma solo cambiaba los textos fijos: lo que escribió el modelo se quedaba en el idioma de la revisión. Muse Spark 1.3 lo traduce una
  vez, al cambiar de idioma. Si pierde una cifra se pide otra vez, y si la inventa o trae un anzuelo, ese texto se queda como estaba.
- **La tarjeta se perdía justo cuando el video traía un anzuelo.** Un paso decía «Ubica la frase “Comparte…”» y el filtro solo reconocía verbos de quitar, así que tiraba
  toda la tarjeta. Ahora señalar lo que el video ya dice no cuenta como sugerirlo, el filtro le dice al modelo en qué campo falló y las instrucciones suben a
  explicar-v9. Sigue en pie que nada que no pase el filtro llega a la persona. No se volvió a medir el juez de tarjetas: esa medición es de una versión anterior.

## 31-oct-2026 · Cuarta medición: apertura-v3 en videos nuevos. Regla escrita antes de medir

- **Por qué.** La revisión del 30-oct encontró dos aperturas reales peores que el original: enumeraban todas las señales y borraban la autoridad de quien habla. Los cuadros 2 y
  3 no los revisaba nadie, y el juez nunca había visto una apertura mala plantada, así que no se sabía si sabe decir que no.
- **Qué cambió (apertura-v3).** Una regla de código rechaza las listas. Conserva la autoridad y los giros del original. Muse Spark 1.3 mira los cuadros que SAM no revisó y, si no
  muestran lo escrito, se corrige. Cifras también en cuadros, magnitudes como «miles» y cifras pegadas («100kg») o compuestas. Spark Open puede decir que el inicio ya funciona, y el
  código lo confirma: sin saludo, sin anzuelo y con el tema en las primeras 12 palabras.
- **Cómo se afinó.** Con 6 casos aparte (`--piloto`, semilla 20261102), corridos dos veces, que no entran a esta medición.
- **Qué se mide** (`eval/apertura_v3.py`, `eval/juez_aperturas.py`, `eval/juez_control.py`). Videos de jul-sep de 2026 de hasta 4 minutos que no están en ninguna medición ni piloto
  anterior, barajados con la semilla 20261101: los primeros 30 cuyo título promete algo que SAM puede comprobar y los primeros 20 que no, de 96 títulos revisados. Sin retención y
  sin video: el título y lo que se dice. La lista quedó fija antes de ver un resultado (sha256 de la lista privada: 6e4aba8e81ff3578ef81616ff958193395dd7cfbd85f256d1cf996d622aee0c0).
- **Regla.** Todas tienen que pasar:
  - A. Al menos 24 de los 30 con promesa pasan todo en 2 correcciones o menos, con SAM encontrando lo prometido, o el inicio se confirma como bueno.
  - B. Al menos 16 de los 20 sin promesa pasan lo mismo menos SAM.
  - C. Trampa lejana: SAM rechaza al menos 9 de 10 cuadros aprobados contra un objeto de otra familia.
  - D. El juez, Muse Spark 1.3, con todo lo que se dice en el video: al menos 80 % de las aperturas aprobadas son fieles.
  - E. El mismo juez: al menos 80 % dejan algo importante para el resto del video.
  - F. El mismo juez compara sin saber cuál es cuál, en los dos órdenes, cada apertura con lo que el video dice en sus primeros 15 segundos. La nueva gana al menos 60 % de los pares
    firmes decididos, con al menos 20 decididos.
  - G. Control negativo: en 10 aperturas con un dato inventado plantado, el juez rechaza al menos 9 por infieles.
  - H. Control negativo: en 10 resúmenes de todo el video usados como apertura, el juez dice en al menos 7 que no deja nada.
  - I. Spark Open no se escapa: como máximo 10 de los 50 inicios se dan por buenos.
- **Se reporta, sin ser condición.** Intervalos de Wilson, trampa cercana, correcciones, fallas, costo y cuántos cuadros revisó Spark.
- **Lo que esto no mide.** Si la apertura nueva retiene más gente. El juez es un modelo, no una persona ni una audiencia. No hay video.
- **Si no pasa.** Se publica igual y no se reajusta en estos casos. Estos 50 casos no se vuelven a usar para esto.
