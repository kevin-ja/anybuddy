FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 1) Dependencias del pipeline
COPY pipelines/ingestion/src/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# 2) Paquete compartido model_loader
COPY packages/model_loader ./packages/model_loader
RUN pip install --no-deps ./packages/model_loader

# 3) Codigo del pipeline (capa que cambia a menudo -> va al final)
COPY pipelines/ingestion ./pipelines/ingestion

WORKDIR /app/pipelines/ingestion

ENTRYPOINT ["python", "-m", "src.ingest"]
