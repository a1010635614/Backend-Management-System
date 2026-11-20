ARG PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.12-slim-bookworm
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
ARG PYTHON_PACKAGE_INDEX=https://pypi.org/simple
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --require-hashes --index-url "$PYTHON_PACKAGE_INDEX" -r requirements.txt \
    && groupadd --gid 10001 blog && useradd --uid 10001 --gid blog --no-create-home blog
COPY --chown=blog:blog backend/app ./app
COPY --chown=blog:blog backend/alembic ./alembic
COPY --chown=blog:blog backend/alembic.ini ./alembic.ini
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "app.server"]
