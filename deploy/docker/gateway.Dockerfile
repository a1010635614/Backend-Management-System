ARG NGINX_IMAGE=public.ecr.aws/docker/library/nginx:stable-alpine
FROM ${NGINX_IMAGE}
COPY deploy/nginx/gateway.conf /etc/nginx/nginx.conf
COPY --chmod=755 deploy/scripts/gateway-entrypoint.sh /usr/local/bin/blog-gateway
USER nginx
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/blog-gateway"]
