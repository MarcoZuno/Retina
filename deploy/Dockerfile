# Demo de Retina: solo archivos estáticos (el panel y casos ya procesados).
# No llama a ninguna API, no recibe videos y no guarda nada. Construir desde la raíz del repo:
#   docker build -f deploy/Dockerfile -t retina-demo .
#   docker run --rm -p 8080:8080 --read-only --tmpfs /tmp --tmpfs /var/cache/nginx retina-demo
FROM nginx:1.27-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY panel/ /usr/share/nginx/html/panel/
COPY casos/ /usr/share/nginx/html/casos/
RUN sed -i 's/^user .*/user nginx;/' /etc/nginx/nginx.conf \
 && sed -i 's#pid .*#pid /tmp/nginx.pid;#' /etc/nginx/nginx.conf
EXPOSE 8080
