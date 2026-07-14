"""
Utilidades AGNOSTICAS de compresion. No saben nada de S3 ni de la ingesta:
solo empaquetan/desempaquetan directorios en .tar.gz. Reusables por cualquier
parte del pipeline (es el espejo de lo que model_loader hace al traer modelos).
"""

import tarfile
from pathlib import Path


def compress_dir(src_dir: Path, dest_tar: Path) -> Path:
    src_dir = Path(src_dir)
    dest_tar = Path(dest_tar)
    dest_tar.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest_tar, "w:gz") as tar:
        tar.add(src_dir, arcname=src_dir.name)
        
    return dest_tar


