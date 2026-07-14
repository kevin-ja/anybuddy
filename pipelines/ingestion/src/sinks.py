"""
Publica el OUTPUT de la Ingestion (el SINK).

Mientras sources.py resuelve los INPUTS (S3 -> local), este modulo hace lo
inverso. La vector DB SIEMPRE se construye en local (chroma_storage/); lo que
cambia segun el entorno es que se hace con ella despues:
- local      -> nada: la DB queda en disco, lista para iterar.
- production -> se comprime a .tar.gz y se publica en S3.

ingest.py no sabe de boto3 ni de tar.gz: solo llama a publish_outputs() y toda
la logica de infraestructura vive aqui.
"""

from model_loader.storage import get_s3_client
from src.config import Settings
from src.utils import compress_dir


def publish_outputs(settings: Settings) -> str | None:
    """
    Publica el output segun el entorno. En production comprime la vector DB y la
    sube a S3, devolviendo la URI s3://. En local no sube nada (devuelve None):
    la DB ya quedo en disco.
    """
    if not settings.vector_db_path.exists():
        raise SystemExit(f"❌ no existe la vector DB en {settings.vector_db_path}")

    # local: la DB ya quedo en chroma_storage/. No se sube nada.
    if settings.is_local:
        print(f"📁 output local listo en {settings.vector_db_path} (no se sube a S3)")
        return None

    # production: comprimir y publicar en S3.
    if not settings.vector_db_s3_bucket:
        raise SystemExit("❌ APP_ENV=production requiere VECTOR_DB_S3_BUCKET")

    name = settings.vector_db_path.name  # p.ej. "chroma_storage"
    tar_path = settings.vector_db_path.parent / f"{name}.tar.gz"

    # normaliza el prefijo: el usuario escribe solo el nombre ("approved" o
    # "approved/" o vacio) y aqui se arma la key con UNA sola barra.
    prefix = settings.vector_db_s3_prefix.strip("/")
    key = f"{prefix}/{name}.tar.gz" if prefix else f"{name}.tar.gz"

    print(f"📦 Comprimiendo {settings.vector_db_path} → {tar_path} ...")
    compress_dir(settings.vector_db_path, tar_path)

    print(f"📤 Subiendo a s3://{settings.vector_db_s3_bucket}/{key} ...")
    get_s3_client(settings.aws_region).upload_file(
        str(tar_path), settings.vector_db_s3_bucket, key
    )

    uri = f"s3://{settings.vector_db_s3_bucket}/{key}"
    print(f"✅ output publicado en {uri}")
    return uri
