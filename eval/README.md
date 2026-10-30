# eval/

Conjunto de prueba, script y resultados. Se mide en cientos de videos de julio a
septiembre de 2026 que el modelo nunca vio; ninguno comparte producción con los
de aprendizaje. Aquí solo quedan métricas agregadas con su intervalo de 95 %,
nunca la lista de videos ni sus curvas.

*Held-out evaluation: aggregated metrics with 95 % intervals only.*

## La apertura arreglada

- `sam_en_dibujos.py`: piloto con temas inventados. ¿SAM 3.1 encuentra objetos en dibujos de Muse Image?
- `apertura_casos.py`: la medición de la regla sellada del 30-oct (`docs/decisiones.md`). No usa retención.
