ARG PYTHON_BUILD_IMAGE=python:3.12-slim
FROM ${PYTHON_BUILD_IMAGE}
ARG PYTHON_PACKAGE_INDEX=https://pypi.org/simple
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url "$PYTHON_PACKAGE_INDEX" -r requirements.txt
COPY app ./app
COPY alembic.ini .
COPY migrations ./migrations
COPY tests ./tests
RUN python -m unittest discover -s tests -v
EXPOSE 8000
CMD ["sh","-c","alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
