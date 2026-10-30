# Retina · cómo desplegar la demo

Para quien despliega. La demo del concurso es la versión simple: el panel de Retina
mostrando casos que ya se procesaron. Son archivos estáticos.

## Qué hace y qué no

- Muestra la tarjeta de Retina de los casos que estén en `casos/` (hoy, el ejemplo `casos/demo/`).
- **No** llama a la API de Meta, **no** recibe videos, **no** guarda datos y **no** necesita llaves.
- Solo responde el panel y los `resultado.json` de `casos/<carpeta>/`; todo lo demás da 404.
- Trae cabeceras de seguridad (CSP, sin incrustarse en otras páginas, sin
  cámara ni micrófono). El panel solo pinta texto: nada del JSON se interpreta como HTML.

## Desplegar

```bash
docker build -f deploy/Dockerfile -t retina-demo .
docker run -d --name retina-demo -p 8080:8080 --read-only \
  --tmpfs /tmp --tmpfs /var/cache/nginx --restart unless-stopped retina-demo
```

Entrar a `http://SERVIDOR:8080/`: abre el panel con el caso de ejemplo. Otro caso:
`/panel/?caso=/casos/NOMBRE/resultado.json`.

Sin Docker sirve cualquier servidor de archivos estáticos con `panel/` y `casos/`, usando las
cabeceras de `deploy/nginx.conf`.

## Agregar casos

Cada caso es una carpeta en `casos/` con su `resultado.json` (formato en `docs/resultado-json.md`).
**Solo casos que se puedan mostrar en público:** videos ya publicados, sin temas de salud ni fuera de alcance, sin
datos de audiencia que no se puedan compartir. Después de agregar, volver a construir la imagen.

## Apagar

```bash
docker stop retina-demo && docker rm retina-demo
```

No queda nada guardado. Para el concurso conviene que siga viva hasta el 16 de noviembre (voto del
público).

## La demo en línea para los jueces

La guía del concurso dice que el jurado también usa el producto en vivo. Esta versión deja que un juez suba su propio video, con
un código de acceso. A diferencia de la demo de arriba, **sí recibe videos, sí llama a las API y sí gasta**. Los créditos del
concurso vencen el 4 de noviembre; después se cobra a la cuenta de las API.

### Qué trae puesto

- Solo responde a su dominio (`RETINA_SITIO`) y solo acepta pedidos de su propia página.
- Código de acceso para subir un video y para arreglar el arranque, comparado en tiempo constante.
- Tope duro: no arranca con `RETINA_TOPE_USD` arriba de 30. Antes de recibir un video revisa que quede presupuesto.
- Videos de hasta 5 minutos y 200 MB, de uno en uno, y máximo 5 en la fila.
- Cada revisión se borra a las 24 horas. Los videos van a la API de Meta y a Baseten para revisarlos.
- Corre con un usuario sin permisos y solo escribe en `/datos`.
- ffmpeg no ve las llaves ni puede salir a la red, y en línea no entran AVI ni FLV.

### Qué necesitas

1. Un servidor con Docker, un dominio y su certificado.
2. La llave de Meta y la de Baseten, con tarjeta si va a seguir viva después del 4 de noviembre.
3. Un código de acceso de al menos 12 caracteres, que se les da a los jueces en el formulario de envío.

### Desplegar

```bash
docker build -f deploy/Dockerfile.en-linea -t retina-en-linea .
docker run -d --name retina-en-linea --restart unless-stopped -p 127.0.0.1:8080:8080 \
  --env-file deploy/en-linea.env --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges \
  --memory 4g --pids-limit 256 -v datos-demo:/datos retina-en-linea
```

El puerto solo se abre a `127.0.0.1`: a internet se llega por el proxy con TLS (`deploy/proxy-en-linea.conf`). Copia
`deploy/en-linea.env.ejemplo` a `deploy/en-linea.env` en el servidor. Ese archivo nunca se sube al repo.

### Revisar y apagar

- Lo gastado está en `/datos/costos.jsonl`, dentro del volumen.
- Para apagarla: `docker stop retina-en-linea`. Para borrar lo que quedó: `docker volume rm datos-demo`.
- ffmpeg lee videos de desconocidos: por eso el contenedor no tiene permisos extra ni memoria sin límite.

