ARG NGINX_IMAGE=public.ecr.aws/docker/library/nginx:stable-alpine
FROM ${NGINX_IMAGE}
ARG FRONTEND=frontend-web
COPY deploy/nginx/static.conf /etc/nginx/nginx.conf
COPY --chown=nginx:nginx ${FRONTEND}/dist/ /usr/share/nginx/html/
USER nginx
EXPOSE 8080
ENTRYPOINT ["nginx", "-g", "daemon off;"]
