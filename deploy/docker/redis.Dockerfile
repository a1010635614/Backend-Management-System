ARG REDIS_IMAGE=public.ecr.aws/docker/library/redis:7.4.11-alpine
FROM ${REDIS_IMAGE}
COPY --chmod=755 deploy/scripts/redis-entrypoint.sh /usr/local/bin/blog-redis
USER redis
ENTRYPOINT ["/usr/local/bin/blog-redis"]
