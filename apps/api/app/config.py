from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # api/tools.py ------------------------------------------------------------
    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    chroma_host: str = Field(alias="CHROMA_HOST")
    chroma_port: int = Field(alias="CHROMA_PORT")

    chroma_collection_name: str = Field(
        alias="CHROMA_COLLECTION_NAME", default="reglamento_anyone_ai"
    )
    reranker_best_n_chunks: int = Field(alias="RERANKER_BEST_N_CHUNKS", default=2)

    # model loader ------------------------------------------------------------
    aws_region: str = Field(alias="AWS_REGION")
    s3_bucket_name: str = Field(alias="S3_BUCKET_NAME")
    embedding_model_s3_key: str = Field(alias="EMBEDDING_MODEL_S3_KEY")
    reranker_model_s3_key: str = Field(alias="RERANKER_MODEL_S3_KEY")
    # model directory inside the container/EBS
    models_cache_dir: Path = Field(alias="MODELS_CACHE_DIR", default=Path("/models"))


settings = Settings()
