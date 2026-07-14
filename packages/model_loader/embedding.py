from .storage import ensure_model

# nombre de la subcarpeta donde se extraera el modelo.
MODEL_NAME = "embedding_model"

__all__ = ["ensure_embedding_model"]


def ensure_embedding_model(cache_dir, *, bucket, key, region):
    """Make the embedding model available locally, fetching it from S3 on a cache miss.

    Thin wrapper over :func:`storage.ensure_model` that fixes the cache
    subdirectory name for the embedding model. The sink (``cache_dir``) and the
    source (``bucket``, ``key``) are mandatory; the package assumes no defaults
    and aborts with an explicit message if any is missing.

    Parameters
    ----------
    cache_dir : str or pathlib.Path
        Sink. Local directory under which the model is cached.
    bucket : str
        Source. Name of the S3 bucket that holds the artifact.
    key : str
        Source. S3 object key of the embedding model artifact.
    region : str
        Source. AWS region where the bucket lives.

    Returns
    -------
    pathlib.Path
        Directory holding the extracted embedding model.
    """
    return ensure_model(
        cache_dir,
        bucket=bucket,
        key=key,
        name=MODEL_NAME,
        region=region,
    )
