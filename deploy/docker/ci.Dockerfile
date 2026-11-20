ARG PYTHON_BUILD_IMAGE=public.ecr.aws/docker/library/python:3.12-slim-bookworm
ARG NODE_BUILD_IMAGE=public.ecr.aws/docker/library/node:22-bookworm-slim
ARG POSTGRES_TEST_IMAGE=public.ecr.aws/docker/library/postgres:16.15-bookworm
FROM ${PYTHON_BUILD_IMAGE} AS python-runtime

# Flow supports build/run, but not network management. Keep real services in one step.
FROM ${POSTGRES_TEST_IMAGE} AS checks
COPY --from=python-runtime /usr/local/ /usr/local/
COPY --from=python-runtime /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
ENV PATH=/usr/local/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN test "$(. /etc/os-release && printf '%s' "$VERSION_CODENAME")" = bookworm \
    && test -s /etc/ssl/certs/ca-certificates.crt \
    && rm -f /etc/apt/sources.list.d/pgdg.list \
    && for source in /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources; do \
         if [ -f "$source" ]; then \
           sed -i -E 's|https?://deb\.debian\.org|https://mirrors.aliyun.com|g' "$source"; \
         fi; \
       done \
    && printf '%s\n' 'Acquire::Retries "2";' 'Acquire::https::Timeout "30";' > /etc/apt/apt.conf.d/80flow-network \
    && apt-get update --error-on=any \
    && apt-get install -y --no-install-recommends \
       bash util-linux ca-certificates libbluetooth3 libbz2-1.0 libdb5.3 \
       libexpat1 libffi8 libgdbm6 libgdbm-compat4 liblzma5 libncursesw6 \
       libreadline8 libsqlite3-0 libssl3 libuuid1 zlib1g redis-server \
    && rm -rf /var/lib/apt/lists/* && ldconfig \
    && python3 -c "import sys,ssl,sqlite3,bz2,lzma,ctypes; assert sys.version_info[:2] == (3,12)"
WORKDIR /workspace
ARG PYTHON_PACKAGE_INDEX=https://pypi.org/simple
COPY backend/requirements-dev.txt ./backend/requirements-dev.txt
RUN pip install --no-cache-dir --require-hashes --index-url "$PYTHON_PACKAGE_INDEX" -r backend/requirements-dev.txt
COPY backend/ ./backend/
COPY deploy/scripts/ ./deploy/scripts/
COPY deploy/tests/ ./deploy/tests/
RUN python3 -m unittest discover -s deploy/tests -v \
    && POSTGRES_BIN=/usr/lib/postgresql/16/bin bash deploy/scripts/test-backend.sh \
    && mkdir /validation && touch /validation/backend-ok

FROM ${NODE_BUILD_IMAGE} AS web
COPY --from=checks /validation/backend-ok /validation/backend-ok
WORKDIR /workspace/frontend-web
COPY frontend-web/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend-web/ ./
ENV VITE_API_BASE_URL=/api VITE_ADMIN_URL=/admin/ VITE_WEB_URL=/
RUN npm test && npm run build

FROM ${NODE_BUILD_IMAGE} AS admin
COPY --from=web /validation/backend-ok /validation/backend-ok
WORKDIR /workspace/frontend-admin
COPY frontend-admin/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend-admin/ ./
ENV VITE_API_BASE_URL=/api VITE_ADMIN_URL=/admin/ VITE_WEB_URL=/
RUN npm test && npm run build

FROM python-runtime AS package
WORKDIR /workspace
COPY backend/app/ ./backend/app/
COPY backend/alembic/ ./backend/alembic/
COPY backend/alembic.ini backend/requirements.txt ./backend/
COPY --from=web /workspace/frontend-web/dist/ ./frontend-web/dist/
COPY --from=admin /workspace/frontend-admin/dist/ ./frontend-admin/dist/
COPY deploy/docker/ ./deploy/docker/
COPY deploy/nginx/ ./deploy/nginx/
COPY deploy/scripts/ ./deploy/scripts/
COPY .env.example docker-compose.yml ./
ARG COMMIT_SHA
RUN python3 deploy/scripts/artifact.py package --commit "$COMMIT_SHA" --root /workspace --artifacts /artifacts

FROM python-runtime AS artifact
COPY --from=package /artifacts/ /artifacts/
CMD ["tar", "-C", "/artifacts", "-czf", "-", "."]
