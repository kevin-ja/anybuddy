"""Download and use of the reranker model.

Same pattern as ``embedding.py``: the download mechanics live in ``storage.py``
and this module is agnostic to the infrastructure. The source (``bucket`` and
``key``) and the sink (``cache_dir``) are always supplied by the consumer. The
reranker is used by the ``api/`` service to re-order the results returned by the
vector store.
"""

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from .storage import ensure_model

# nombre de la carpeta donde se extrae en el cache local (detalle interno, no es
# una ruta de infraestructura).
MODEL_NAME = "reranker_model"

__all__ = ["ensure_reranker_model", "Reranker"]


def ensure_reranker_model(cache_dir, *, bucket, key, region):
    """Make the reranker model available locally, fetching it from S3 on a cache miss.

    Thin wrapper over :func:`storage.ensure_model` that fixes the cache
    subdirectory name for the reranker model. The sink (``cache_dir``) and the
    source (``bucket``, ``key``) are mandatory; the package assumes no defaults
    and aborts with an explicit message if any is missing.

    Parameters
    ----------
    cache_dir : str or pathlib.Path
        Sink. Local directory under which the model is cached.
    bucket : str
        Source. Name of the S3 bucket that holds the artifact.
    key : str
        Source. S3 object key of the reranker model artifact.
    region : str
        Source. AWS region where the bucket lives.

    Returns
    -------
    pathlib.Path
        Directory holding the extracted reranker model.
    """
    return ensure_model(
        cache_dir,
        bucket=bucket,
        key=key,
        name=MODEL_NAME,
        region=region,
    )