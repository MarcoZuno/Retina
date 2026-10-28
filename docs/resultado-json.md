# resultado.json · lo que lee el panel (retina-v1)

El panel solo lee este archivo. Si le falta un campo, se agrega en el
orquestador (`src/retina/retina.py`); el panel no inventa campos.
Ejemplo inventado, sin datos reales: [`casos/demo/resultado.json`](../casos/demo/resultado.json).

*The panel reads only this file. The example is made up, with no real data.*

## Lo que muestra la tarjeta

| Campo | Qué es | Cómo se muestra |
|---|---|---|
| `arranque.nivel` | `alto`, `medio` o `bajo`: si el gancho y el primer cuarto del video van a perder más gente que videos parecidos. | El titular de la tarjeta (textos abajo). |
| `explicacion.por_que` | Dos frases como máximo, con los segundos donde pasa. | Debajo del titular. |
| `explicacion.que_cambiar` | Un solo cambio de edición o guion. Vacío si el nivel es `bajo` o si ninguna sugerencia pasó los filtros. | Caja «Qué cambiar». Si viene vacío y el nivel no es `bajo`, mostrar `no_pude_verificar`. |
| `explicacion.momento_s` | Segundo donde empieza lo que hay que cambiar. Siempre dentro del arranque. | Marca en la línea de tiempo. |
| `explicacion.lo_que_funciona` | Lo que el arranque ya hace bien. Puede venir vacío. | Línea en verde, opcional. |
| `explicacion.anzuelo_detectado` | `ninguno` o el id de la regla (ver `reglas/anzuelos-v1.json`) si el borrador ya trae algo que Meta castiga. | Tarjeta roja con el nombre y la fuente de la regla. |
| `explicacion.storyboard` | Tres cuadros en texto. Las imágenes salen aparte con `retina.storyboard --aprobar`. | Botón «Ver storyboard». |
| `explicacion.confianza` | `baja`, `media` o `alta`. | Junto a la explicación. |
| `licencia.comparado_con`, `licencia.datos_hasta`, `licencia.no_pude_revisar` | Contra qué se comparó y lo que no se revisó. | Línea de confianza al pie. |

Textos del titular, en el lenguaje de quien publica:

- `alto`: «Tu arranque puede perder más gente que tus videos parecidos».
- `medio`: «Tu arranque se puede mejorar».
- `bajo`: «Tu arranque va como tus videos parecidos o mejor».

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
