"""Shared mechanics for fetching models from object storage.

The current backend is Amazon S3, but every AWS dependency is isolated in this
module: if the storage provider changes, this is the only file that must be
modified. The ``embedding`` and ``reranker`` modules only declare *what* to
download (bucket and key); this module knows *how* to download it.
"""

import pathlib
import tarfile

import boto3
from botocore.exceptions import ClientError


def get_s3_client(region: str):
    """Build an S3 client for the given region.

    Parameters
    ----------
    region : str
        AWS region the client targets (e.g. ``"us-east-2"``).

    Returns
    -------
    botocore.client.S3
        Ready-to-use S3 client.
    """
    return boto3.client("s3", region_name=region)


def ensure_model(
    cache_dir, *, bucket: str, key: str, name: str, region: str
) -> pathlib.Path:
    """Download a model artifact from S3 and unpack it into a given local directory.

    Validates that the sink (``cache_dir``) and source (``bucket``, ``key``) are
    provided, then downloads the ``.tar.gz`` artifact and extracts it under
    ``cache_dir/name``, removing the tarball afterwards. The operation is
    idempotent: if that directory already exists and is non-empty, the cached
    copy is reused and nothing is downloaded.

    Parameters
    ----------
    cache_dir : str or pathlib.Path
        Sink. Local directory under which the model is downloaded and
        extracted. Created if it does not exist.
    bucket : str
        Source. Name of the S3 bucket that holds the artifact.
    key : str
        Source. S3 object key of the ``.tar.gz`` artifact to download.
    name : str
        Logical model name, used as the cache subdirectory and in log
        messages.
    region : str
        Source. AWS region where the bucket lives. Mandatory: the package
        resolves no region by itself.

    Returns
    -------
    pathlib.Path
        Directory holding the extracted model, ready for ``transformers`` /
        ``sentence-transformers``.

    Raises
    ------
    ValueError
        If the sink (``cache_dir``) or any part of the source (``bucket``,
        ``key``, ``region``) is missing.
    botocore.exceptions.ClientError
        If the artifact cannot be downloaded from S3.
    """
    if not cache_dir:
        raise ValueError(
            f"model_loader: falta el SINK (cache_dir) para '{name}'. "
            "Indica en que carpeta local debe descargarse el modelo. "
            "El paquete no define rutas por defecto: pasalo desde tu script/config."
        )
    if not bucket or not key or not region:
        faltan = ", ".join(
            etiqueta
            for etiqueta, valor in (
                ("bucket", bucket),
                ("key", key),
                ("region", region),
            )
            if not valor
        )
        raise ValueError(
            f"model_loader: falta el SOURCE ({faltan}) para '{name}'. "
            "Indica de que bucket y con que key bajar el artefacto. "
            "El paquete no define coordenadas por defecto: pasalas desde tu script/config."
        )

    cache = pathlib.Path(cache_dir)
    model_dir = cache / name

    if model_dir.exists() and any(model_dir.iterdir()):
        print(f"✅ {name} ya en cache: {model_dir}")
        return model_dir

    cache.mkdir(parents=True, exist_ok=True)
    tar_path = cache / f"{name}.tar.gz"

    print(f"📦 Descargando {key} desde s3://{bucket} ...")
    try:
        get_s3_client(region).download_file(bucket, key, str(tar_path))
    except ClientError as e:
        print(f"❌ Error al descargar {name}: {e}")
        raise

    with tarfile.open(tar_path) as tar:
        tar.extractall(model_dir)
    tar_path.unlink()

    print(f"📂 {name} listo en: {model_dir}")
    return model_dir
