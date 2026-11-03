# eval/

Conjunto de prueba, script y resultados. Se mide en cientos de videos de julio a
septiembre de 2026 que el modelo nunca vio; ninguno comparte producción con los
de aprendizaje. Aquí solo quedan métricas agregadas con su intervalo de 95 %,
nunca la lista de videos ni sus curvas.

*Held-out evaluation: aggregated metrics with 95 % intervals only.*

## La apertura arreglada

- `sam_en_dibujos.py`: piloto con temas inventados. ¿SAM 3.1 encuentra objetos en dibujos de Muse Image?
- `apertura_casos.py`: la medición de la regla sellada del 30-oct (`docs/decisiones.md`). No usa retención.
- `apertura_nuevos.py`: la segunda medición, con el vocabulario calibrado de SAM. Es una regresión, no una validación (`docs/results.md`).
- `apertura_v2.py`: la tercera medición, con apertura-v2, un grupo sin promesa visible y trampas cercanas.
- `juez_aperturas.py`: juez ciego de las aperturas: fieles al video, dejan algo al resto y contra el arranque real.
- `delta_numero.py`: exploratorio. El número antes y después de reescribir el arranque, sin retención real.
- `margen_numero.py`: de cuánto suele ser el error del número, con creadores escondidos. De aquí sale el margen del panel.

- `apertura_v3.py`, `juez_control.py`: cuarta medición de la apertura, con los tres dibujos revisados y control negativo del juez.
- `apertura_v4.py`: quinta medición, la de la versión que se publica: solo videos dentro del alcance de Retina, con lectura de fidelidad en el producto. Usa `juez_aperturas.py` y `juez_control.py`.
- `tacticas_gancho.py`: descriptivo, sin regla. Qué tácticas de arranque van con más retención entre videos distintos. No prueba la reescritura.

## Lo demás que hay en esta carpeta

Los otros 18 scripts son investigación o apoyo. Ninguno fija una cifra de las que salen en el panel. Entre paréntesis, dónde está escrito
lo que salió de cada uno: `docs/results.md`, `docs/decisiones.md` (ahí va la regla cuando la hay) o `BUILD-LOG.md`, el diario día por día.

- `linea_base.py`: la regla de «videos parecidos» medida en los videos de prueba. Es la referencia que todo lo demás tiene que superar (`BUILD-LOG.md`).
- `escala.py`: cuánto ayuda entrenar con más años de videos, medido siempre en los mismos videos de prueba (`BUILD-LOG.md`).
- `tramo_v1.py`: tres formas de ubicar el tramo donde se va más gente de lo normal, con los vectores de V-JEPA 2. Ninguna le ganó
  a la moda, y por eso Retina no presume ubicar ese tramo (`BUILD-LOG.md`).
- `voz_tramo.py` y `voz_gancho.py`: lo mismo con lo que se dice (transcripción con tiempos) en vez de lo que se ve, y si la voz del
  arranque explica cuánta gente se queda (`BUILD-LOG.md`).
- `arranque_con_video.py`: si lo que ya se mide del video en local mejora el nivel de riesgo del arranque. Regla del 28-oct
  (`docs/decisiones.md`, `BUILD-LOG.md`).
- `casos_api.py`: Retina de punta a punta, con la API, en 50 videos ya publicados que los modelos no vieron. De aquí salen los casos
  que usan los jueces y las comparaciones de abajo (`BUILD-LOG.md`).
- `prediccion_vs_real.py`: en esos 50 casos, la curva que predijo Retina y la regla contra la curva real. No llama a ninguna API (`BUILD-LOG.md`).
- `juez_pares.py`: juez ciego por pares. ¿Mirar el arranque de dos videos dice cuál perdió más gente que sus parecidos? Cada par en
  los dos órdenes (`BUILD-LOG.md`).
- `casos_agente.py`, `casos_spark_open.py` y `juez_tarjetas.py`: la tarjeta escrita por el agente contra una sola vuelta, Spark Open
  contra Spark 1.3, y el juez ciego entre las dos (`docs/results.md`, «The card and the agent»; la regla del juez en `docs/decisiones.md`).
- `cualquier_video.py`: ¿sirve con un creador que nunca vio? Los talentos se esconden por grupos y entran como entraría uno de fuera
  (`docs/decisiones.md`, `BUILD-LOG.md`).
- `revision_meta_casos.py`: si los videos que fallan una recomendación de Meta perdieron más gente al inicio. Con 50 casos es una
  pista, no una prueba (`docs/decisiones.md`).
- `semaforo_publico.py` y `semaforo_publico_v2.py`: el semáforo del cerebro público en periodos que no vio. La v1 no pasó su regla y
  la v2 no entró al producto (`docs/decisiones.md`, `BUILD-LOG.md`).
- `calibrar_vocabulario.py` y `sam_objetos_dificiles.py`: qué palabras de la lista cerrada encuentra SAM 3.1 en dibujos de Muse Image,
  y por qué falla con algunas. Escenas inventadas, sin datos de nadie (`docs/decisiones.md`).
