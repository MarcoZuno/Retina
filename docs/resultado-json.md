# resultado.json · lo que lee el panel (retina-v1)

El panel solo lee este archivo. Si le falta un campo, se agrega en el
orquestador (`src/retina/retina.py`); el panel no inventa campos.
Ejemplo inventado, sin datos reales: [`casos/demo/resultado.json`](../casos/demo/resultado.json).

*The panel reads only this file. The example is made up, with no real data.*

## Lo que muestra la tarjeta

`explicacion` la escribe el agente (`--con-api --voz`) o, sin `--voz`, `explicar` de una
vuelta. Los dos dan los mismos campos; `explicacion.licencia.fuente` dice cuál fue
(`agente` o `explicar (respaldo)`) y `licencia.traza` lista las herramientas que usó.

| Campo | Qué es | Cómo se muestra |
|---|---|---|
| `arranque.nivel` | `alto`, `medio` o `bajo`: si el gancho y el primer cuarto del video van a perder más gente que videos parecidos de su mismo tipo de producción (`arranque.comparado_con_su_tipo`). | El titular de la tarjeta (textos abajo). |
| `explicacion.por_que` | Dos frases como máximo, con los segundos donde pasa. | Debajo del titular. |
| `explicacion.que_cambiar` | Un solo cambio de edición o guion. Vacío si el nivel es `bajo` o si ninguna sugerencia pasó los filtros. | Caja «Qué cambiar». Si viene vacío y el nivel no es `bajo`, mostrar `no_pude_verificar`. |
| `explicacion.momento_s` | Segundo donde empieza lo que hay que cambiar. Siempre dentro del arranque. | Marca en la línea de tiempo, en m:ss. Si es menor que 1, «desde el primer segundo» y sin marca. |
| `explicacion.lo_que_funciona` | Lo que el arranque ya hace bien. Puede venir vacío. | Línea en verde, opcional. |
| `explicacion.anzuelo_detectado` | `ninguno` o el id de la regla (ver `reglas/anzuelos-v1.json`) si el video ya trae algo que Meta castiga. | Tarjeta roja. |
| `explicacion.pasos` | De 1 a 4 pasos, en orden, para hacer el cambio en el editor; cada uno una acción con su segundo. Vacío si no hay cambio. | Lista numerada debajo de «Qué hacer», con los segundos como 0:05. |
| `explicacion.anzuelo_frase`, `explicacion.anzuelo_momento_s` | La frase o lo que se ve, y el segundo donde aparece (-1 si no hay anzuelo). | «En 0:25: Comparte esta información…». Si hay anzuelo, `que_cambiar` siempre dice cómo quitarlo. |
| `explicacion.storyboard` | Tres cuadros en texto. Las imágenes salen aparte con `retina.storyboard --aprobar`. | Botón «Ver storyboard». |
| `explicacion.confianza` | `baja`, `media` o `alta`. | Junto a la explicación. |
| `licencia.comparado_con`, `licencia.datos_hasta`, `licencia.no_pude_revisar` | Contra qué se comparó y lo que no se revisó. | Línea de confianza al pie. |

Textos del titular, en el lenguaje de quien publica:

- `alto`: «Tu arranque puede perder más gente que tus videos parecidos».
- `medio`: «Tu arranque se puede mejorar».
- `bajo`: «No vemos un problema claro en tu arranque» (en gris, no en verde: en «bajo» también hay videos que pierden de más, solo que menos).

## La línea de tiempo

- `prediccion.curva_predicha` y `prediccion.curva_parecidos`: 41 puntos, del 0 al
  100 % del video (punto *k* = `k / 40 × video.duracion_s` segundos). Gris la
  predicha, punteada la de parecidos.
- La banda ámbar cubre **el arranque completo**: tramos 0 a 10, es decir del 0 al
  25 % del video. No se marca un tramo ni un bloque como «el peor»: eso no se
  sostuvo en las pruebas (ver `docs/decisiones.md`, 27-oct noche).
- `arranque.bloques`: 5 bloques con `tramos` [inicio, fin) y la caída típica de los
  videos parecidos en ese bloque. Sirve de contexto («en videos así, en el gancho
  se va el 30 % de la gente»), no como predicción.

## Lo que el panel no debe usar

`prediccion.tramo_riesgo`, `prediccion.caida_predicha_pp` y
`prediccion.caida_parecidos_pp` siguen en el archivo por compatibilidad, pero
ya no se prometen: el tramo exacto pasado el arranque es ruido de redondeo.

## Lo que el validador garantiza en el texto

`por_que`, `lo_que_funciona` y `que_cambiar` nunca traen «pp», porcentajes, «s0.6»,
«tramo» ni nombres técnicos; miden 220 caracteres como máximo; los segundos vienen
como «segundo 4». El panel puede mostrarlos tal cual, siempre como texto
(`textContent`), nunca como HTML.

## El panel (desde el 28-oct)

`panel/index.html` lee este archivo y lo muestra en lenguaje de quien edita: semáforo («Alerta»,
«Se puede mejorar», «Sin problema claro»), una sola cifra («59 de cada 100 personas seguirán viendo a
los 15 segundos; en videos parecidos, 62»), la barra del inicio con las partes a revisar (los tramos
«del segundo A al B» que cita `por_que`), «Qué hacer» con los `pasos` y un botón para copiarlos al
editor, y lo técnico escondido en «Ver detalle». Los segundos se muestran como reloj (0:05).
`python -m retina.demo` lo abre con un caso, sin llave.

`realidad.curva` (opcional, 41 puntos): la curva real de un video ya publicado. Si viene, el panel
la dibuja junto a la predicción y dice cuántos siguieron de verdad. Es para la demo «predicción
contra realidad»; un video sin publicar no la trae.
