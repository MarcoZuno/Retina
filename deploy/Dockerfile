# Demo de Retina: solo archivos estáticos (el panel y casos ya procesados).
# No llama a ninguna API, no recibe videos y no guarda nada. Construir desde la raíz del repo:
#   docker build -f deploy/Dockerfile -t retina-demo .
#   docker run --rm -p 127.0.0.1:8080:8080 --read-only --cap-drop ALL --security-opt no-new-privileges \n#     --tmpfs /tmp:uid=101,gid=101 --tmpfs /var/cache/nginx:uid=101,gid=101 retina-demo
FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY panel/ /usr/share/nginx/html/panel/
COPY casos/ /usr/share/nginx/html/casos/
RUN sed -i 's/^user .*/user nginx;/' /etc/nginx/nginx.conf \
 && sed -i 's#pid .*#pid /tmp/nginx.pid;#' /etc/nginx/nginx.conf
USER nginx
EXPOSE 8080
