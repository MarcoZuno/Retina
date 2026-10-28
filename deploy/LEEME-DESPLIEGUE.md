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
**Solo casos aprobados:** videos ya publicados, sin temas de salud ni fuera de alcance, sin
datos de audiencia que no se hayan autorizado. Después de agregar, volver a construir la imagen.

## Apagar

```bash
docker stop retina-demo && docker rm retina-demo
```

No queda nada guardado. Para el concurso conviene que siga viva hasta el 16 de noviembre (voto del
público).

## Lo que no es esto

La Retina completa (subir un video, que Spark lo revise y escriba la tarjeta) necesita la llave de
Meta, ffmpeg y una cola de trabajos. Eso es para después del concurso, en un servidor propio.
