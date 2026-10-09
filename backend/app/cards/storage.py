"""Закрытое файловое хранилище; каталог задаёт доверенная конфигурация (T-11 / SR-24)."""

import os
from pathlib import Path
from uuid import uuid4


def store_material(data: bytes, directory: Path) -> str:
    """Пишет новый файл 0600 без перезаписи; при сбое удаляет незавершённый файл."""
    storage_key = uuid4().hex
    path = directory / storage_key
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return storage_key
