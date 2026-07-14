"""
Segun el entorno (local vs prod) resuelve rutas donde se almacenarn los inputs 
de la Ingestion:
- Modelo de embedding (siempre del mismo bucket S3, centralizado)
- knowledge_base: faqs.txt (local: disco; prod: S3)

El OUTPUT (la vector DB comprimida -> S3) NO vive aqui: es el SINK y se resuelve
en sinks.py (publish_outputs).

ingest.py NO sabe si corre en local o en prod: solo llama a ensure_inputs() y
recibe rutas/refs LOCALES ya listas para usar. Toda la logica vive aqui, de modo
que el pipeline queda agnostico a la infraestructura.

- modelo de embedding: SIEMPRE se baja del MISMO bucket S3 (local y prod).
                       Centralizado e idempotente: si ya esta en cache, no baja.
- faqs.txt:            local -> se lee del disco (lo estas editando);
                       prod  -> se baja de S3.
"""

from dataclasses import dataclass
from pathlib import Path
from model_loader.embedding import ensure_embedding_model
from model_loader.storage import get_s3_client
from src.config import Settings


@dataclass(frozen=True)
class ResolvedInputs:
    knowledge_path: Path  # SOURCE: knowledge_base
    model_ref: str  # SOURCE: embedding_model


def ensure_inputs(settings: Settings) -> ResolvedInputs:
    settings.model_cache_dir.mkdir(parents=True, exist_ok=True)

    # embedding_model
    model_dir = ensure_embedding_model(
        settings.model_cache_dir,
        bucket=settings.s3_bucket,
        key=settings.embedding_model_s3_key,
        region=settings.aws_region,
    )

    # knowledge_base: faqs.txt
    knowledge_path = _resolve_knowledge(settings)

    return ResolvedInputs(
        knowledge_path=knowledge_path,
        model_ref=str(model_dir)
    )


def _resolve_knowledge(settings: Settings) -> Path:
    # LOCAL/DEV ENV
    if settings.is_local:
        if not settings.knowledge_path.exists():
            raise SystemExit(
                f"❌ knowledge base no encontrado en {settings.knowledge_path}\n"
                f"   coloca tu faqs.txt ahi (o exporta KNOWLEDGE_PATH)."
            )
        return settings.knowledge_path

    # PROD ENV
    if not settings.s3_bucket:
        raise SystemExit("❌ APP_ENV=production requiere S3_BUCKET")

    settings.knowledge_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"📥 S3 → {settings.knowledge_s3_key}")
    get_s3_client(settings.aws_region).download_file(
        settings.s3_bucket, settings.knowledge_s3_key, str(settings.knowledge_path)
    )
    
    return settings.knowledge_path
