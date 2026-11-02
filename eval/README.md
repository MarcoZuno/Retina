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
