from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings

# pipelines/ingestion/
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # --- APP MODE ---
    app_env: Literal["local", "production"] = Field(alias="APP_ENV", default="local")
    # only for testing
    openai_api_key: str = Field(alias="OPENAI_API_KEY", default="")

    # --- LOCAL/DEV PATHS --
    knowledge_path: Path = Field(
        alias="KNOWLEDGE_PATH", default=BASE_DIR / "knowledge_base" / "faqs.txt"
    )
    model_cache_dir: Path = Field(
        alias="MODEL_CACHE_DIR", default=BASE_DIR / "models"
    )
    vector_db_path: Path = Field(
        alias="VECTOR_DB_PATH", default=Path("/data/chroma_storage")
    )

    # --- AWS S3 SOURCES ---
    aws_region: str = Field(alias="AWS_REGION")
    s3_bucket: str = Field(alias="S3_BUCKET")
    knowledge_s3_key: str = Field(alias="KNOWLEDGE_S3_KEY")
    embedding_model_s3_key: str = Field(
        alias="EMBEDDING_MODEL_S3_KEY", default="models/embedding_model.tar.gz"
    )

    # --- AWS S3 SINK ---
    vector_db_s3_bucket: str = Field(alias="VECTOR_DB_S3_BUCKET", default="")
    vector_db_s3_prefix: str = Field(alias="VECTOR_DB_S3_PREFIX", default="")

    # --- EMBEDDING & VECTOR DB CONFIG ---
    chroma_collection_name: str = Field(
        alias="CHROMA_COLLECTION_NAME", default="reglamento_anyone_ai"
    )
    # similitud Coseno
    hnsw_space: str = Field(alias="HNSW_SPACE", default="cosine")
    # 16 amigos por nodo
    hnsw_m: int = Field(alias="HNSW_M", default=16)
    # 100 entrevistas en la ingesta
    hnsw_construction_ef: int = Field(alias="HNSW_CONSTRUCTION_EF", default=100)
    # Linterna de 50 sospechosos en el suelo
    hnsw_search_ef: int = Field(alias="HNSW_SEARCH_EF", default=50)

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"


settings = Settings()
