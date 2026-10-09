"""Проверка синтетических материалов до записи на диск (задача 4.3)."""

import hashlib
import re
import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath

import pymupdf
from PIL import Image, UnidentifiedImageError

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 30
FORMATS = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
PDF_UNSAFE_NAMES = re.compile(r"/(?:JavaScript|JS|EmbeddedFiles?|Filespec|FileAttachment|EF)\b")


class MaterialRejected(ValueError):
    """Безопасная причина отказа без имени, содержимого или деталей парсера."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class MaterialMetadata:
    """Метаданные проверенного материала для будущей записи в БД."""

    mime: str
    size: int
    sha256: str
    pages: int


def validate_material(data: bytes, *, filename: str, declared_mime: str) -> MaterialMetadata:
    """Проверяет формат, лимиты и структуру; не сохраняет и не журналирует данные."""
    # Ресурсные лимиты до парсинга: T-16 / SR-25.
    if not data or len(data) > MAX_FILE_BYTES:
        raise MaterialRejected("invalid_size")
    if (
        not filename
        or any(ord(char) < 32 for char in filename)
        or "/" in filename
        or "\\" in filename
        or len(PurePath(filename).suffixes) != 1
    ):
        raise MaterialRejected("invalid_filename")
    suffix = PurePath(filename).suffix.lower()
    mime = FORMATS.get(suffix)
    if mime is None or declared_mime != mime:
        raise MaterialRejected("invalid_type")
    signature_matches = {
        "application/pdf": data.startswith(b"%PDF-"),
        "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": data.startswith(b"\xff\xd8\xff"),
    }
    if not signature_matches[mime]:
        raise MaterialRejected("invalid_type")
    pages = _validate_pdf(data) if mime == "application/pdf" else _validate_image(data, mime)
    return MaterialMetadata(mime=mime, size=len(data), sha256=hashlib.sha256(data).hexdigest(), pages=pages)


def _validate_pdf(data: bytes) -> int:
    """Проверяет разобранные объекты, включая косвенные и экранированные PDF-имена."""
    try:
        with pymupdf.open(stream=data, filetype="pdf") as document:
            if document.needs_pass or document.xref_get_key(-1, "Encrypt")[0] != "null":
                raise MaterialRejected("encrypted_pdf")
            if document.is_repaired:
                raise MaterialRejected("invalid_pdf")
            if not 1 <= document.page_count <= MAX_PDF_PAGES:
                raise MaterialRejected("invalid_page_count")
            if document.embfile_count():
                raise MaterialRejected("unsafe_pdf")
            for xref in range(1, document.xref_length()):
                # MuPDF нормализует #XX в именах; поиск по исходным bytes обходился бы /J#53.
                # Консервативный отказ также при маркере в строковом значении объекта.
                if PDF_UNSAFE_NAMES.search(document.xref_object(xref, compressed=False)):
                    raise MaterialRejected("unsafe_pdf")
            for page in document:
                page.get_contents()
            return document.page_count
    except MaterialRejected:
        raise
    except (RuntimeError, ValueError) as exc:
        raise MaterialRejected("invalid_pdf") from exc


def _validate_image(data: bytes, mime: str) -> int:
    """Проверяет целостность и декодирование; bomb-warning Pillow считается отказом."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format != ("PNG" if mime == "image/png" else "JPEG"):
                    raise MaterialRejected("invalid_type")
                image.verify()
            with Image.open(BytesIO(data)) as image:
                image.load()
        return 1
    except MaterialRejected:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise MaterialRejected("invalid_image") from exc
