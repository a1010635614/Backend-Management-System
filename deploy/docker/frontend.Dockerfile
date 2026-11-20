ARG NODE_IMAGE=public.ecr.aws/docker/library/node:22-bookworm-slim
ARG NGINX_IMAGE=public.ecr.aws/docker/library/nginx:stable-alpine
FROM ${NODE_IMAGE} AS build
ARG FRONTEND=frontend-web
WORKDIR /app
COPY ${FRONTEND}/package.json ${FRONTEND}/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY ${FRONTEND}/ ./
ENV VITE_API_BASE_URL=/api VITE_ADMIN_URL=/admin/ VITE_WEB_URL=/
RUN npm run build

FROM ${NGINX_IMAGE}
COPY deploy/nginx/static.conf /etc/nginx/nginx.conf
COPY --from=build --chown=nginx:nginx /app/dist /usr/share/nginx/html
USER nginx
EXPOSE 8080
ENTRYPOINT ["nginx", "-g", "daemon off;"]
