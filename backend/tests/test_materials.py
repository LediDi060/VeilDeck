"""Негативные проверки подготовки материалов: задачи 4.3 / 4.6, TC-CARD / TC-RBAC."""

import hashlib
import os
from contextlib import contextmanager
from io import BytesIO
from uuid import UUID, uuid4

import pymupdf
import pytest
from PIL import Image

from app.cards import storage
from app.cards.material_validation import MAX_FILE_BYTES, MaterialRejected, validate_material
from app.cards.service import prepare_material
from app.core.exceptions import Forbidden
from app.core.principal import Principal, Role


def image_bytes(format_name="PNG"):
    """Создаёт маленькое синтетическое изображение."""
    buffer = BytesIO()
    Image.new("RGB", (16, 16)).save(buffer, format=format_name)
    return buffer.getvalue()


def pdf_bytes(pages=1, unsafe=None, password=None):
    """Создаёт синтетический PDF, при необходимости — с опасным объектом."""
    with pymupdf.open() as document:
        for _ in range(pages):
            document.new_page()
        if unsafe == "attachment":
            document.embfile_add("synthetic.txt", b"SYNTHETIC")
        elif unsafe == "annotation":
            document[0].add_file_annot((20, 20), b"SYNTHETIC", "synthetic.txt")
        elif unsafe:
            action = document.get_new_xref()
            document.update_object(action, unsafe)
            document.xref_set_key(document.pdf_catalog(), "OpenAction", f"{action} 0 R")
        options = {}
        if password is not None:
            options = {"encryption": pymupdf.PDF_ENCRYPT_AES_256, "owner_pw": "synthetic-owner", "user_pw": password}
        return document.tobytes(**options)


def prepare(data, directory, *, filename="synthetic.pdf", mime="application/pdf", role=Role.ADMIN):
    """Вызывает внутренний сервис с тестовым субъектом."""
    return prepare_material(
        Principal(subject_id=uuid4(), role=role),
        data=data,
        filename=filename,
        declared_mime=mime,
        storage_directory=directory,
    )


@pytest.mark.parametrize(
    ("filename", "mime", "data"),
    [
        ("synthetic.pdf", "application/pdf", pdf_bytes()),
        ("synthetic.PNG", "image/png", image_bytes()),
        ("synthetic.jpg", "image/jpeg", image_bytes("JPEG")),
        ("synthetic.jpeg", "image/jpeg", image_bytes("JPEG")),
    ],
)
def test_material_stored_with_random_key_and_metadata(tmp_path, filename, mime, data):
    """Метаданные соответствуют bytes; имя пользователя не становится путём (SR-24)."""
    first = prepare(data, tmp_path, filename=filename, mime=mime)
    second = prepare(data, tmp_path, filename=filename, mime=mime)
    assert UUID(hex=first.storage_key).version == 4
    assert first.storage_key != second.storage_key
    path = tmp_path / first.storage_key
    assert path.read_bytes() == data
    assert path.stat().st_mode & 0o777 == 0o600
    assert first.metadata.mime == mime
    assert first.metadata.size == len(data)
    assert first.metadata.sha256 == hashlib.sha256(data).hexdigest()
    assert first.metadata.pages == 1
    assert not (tmp_path / filename).exists()


@pytest.mark.parametrize("role", [Role.REVIEWER, Role.VIEWER])
def test_tc_rbac_material_preparation_admin_only(tmp_path, role):
    """Отказ по роли происходит даже до разбора повреждённого файла (T-07 / SR-16)."""
    with pytest.raises(Forbidden):
        prepare(b"not a document", tmp_path, role=role)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("filename", "mime", "data", "reason"),
    [
        ("report.pdf.exe", "application/pdf", pdf_bytes(), "invalid_filename"),
        ("report.exe.pdf", "application/pdf", pdf_bytes(), "invalid_filename"),
        ("../report.pdf", "application/pdf", pdf_bytes(), "invalid_filename"),
        ("C:\\report.pdf", "application/pdf", pdf_bytes(), "invalid_filename"),
        ("report\x00.pdf", "application/pdf", pdf_bytes(), "invalid_filename"),
        ("report.pdf", "application/pdf", image_bytes(), "invalid_type"),
        ("report.png", "application/pdf", image_bytes(), "invalid_type"),
        ("report.pdf", "application/octet-stream", pdf_bytes(), "invalid_type"),
        ("report.svg", "image/svg+xml", b"<svg/>", "invalid_type"),
        ("report.png", "image/png", b"\x89PNG\r\n\x1a\ninvalid", "invalid_image"),
        ("report.jpg", "image/jpeg", image_bytes("JPEG")[:-20], "invalid_image"),
        ("report.pdf", "application/pdf", b"%PDF-invalid", "invalid_pdf"),
        ("report.pdf", "application/pdf", b"", "invalid_size"),
        ("report.pdf", "application/pdf", b"x" * (MAX_FILE_BYTES + 1), "invalid_size"),
    ],
)
def test_tc_card_invalid_upload_never_written(tmp_path, filename, mime, data, reason):
    """Подмены формата, повреждения и превышение размера не оставляют файл."""
    with pytest.raises(MaterialRejected) as error:
        prepare(data, tmp_path, filename=filename, mime=mime)
    assert error.value.reason == reason
    assert str(error.value) == reason
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "unsafe",
    [
        "attachment",
        "annotation",
        r"<< /S /JavaScript /JS (app.alert\(1\)) >>",
        r"<< /S /Java#53cript /J#53 (app.alert\(1\)) >>",
        "<< /Next << /S /JavaScript /JS (synthetic) >> >>",
    ],
)
def test_tc_card_pdf_active_content_never_written(tmp_path, unsafe):
    """Вложения, косвенные действия и #XX-имена не обходят структурный разбор."""
    with pytest.raises(MaterialRejected, match="unsafe_pdf"):
        prepare(pdf_bytes(unsafe=unsafe), tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("password", ["synthetic-password", ""])
def test_tc_card_encrypted_pdf_rejected(tmp_path, password):
    """Шифрование отклоняется даже если пароль открытия пустой."""
    with pytest.raises(MaterialRejected, match="encrypted_pdf"):
        prepare(pdf_bytes(password=password), tmp_path)
    assert not list(tmp_path.iterdir())


def test_tc_card_page_limit(tmp_path):
    """Граница 30 страниц включительно; 31 страница не сохраняется."""
    assert prepare(pdf_bytes(pages=30), tmp_path).metadata.pages == 30
    with pytest.raises(MaterialRejected, match="invalid_page_count"):
        prepare(pdf_bytes(pages=31), tmp_path)
    assert len(list(tmp_path.iterdir())) == 1


def test_tc_card_size_boundary():
    """Ровно 10 МиБ допускается без ошибки на границе."""
    data = image_bytes()
    data += b"\0" * (MAX_FILE_BYTES - len(data))
    assert validate_material(data, filename="synthetic.png", declared_mime="image/png").size == MAX_FILE_BYTES


def test_tc_card_image_bomb_rejected(tmp_path, monkeypatch):
    """Предупреждение декодера о bomb становится отказом (T-16)."""
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 200)
    with pytest.raises(MaterialRejected, match="invalid_image"):
        prepare(image_bytes(), tmp_path, filename="synthetic.png", mime="image/png")
    assert not list(tmp_path.iterdir())


def test_tc_card_png_crc_rejected(tmp_path):
    """Повреждённая контрольная сумма PNG даёт безопасный отказ, а не SyntaxError."""
    data = bytearray(image_bytes())
    data[data.index(b"IDAT") + 4] ^= 1
    with pytest.raises(MaterialRejected, match="invalid_image"):
        prepare(bytes(data), tmp_path, filename="synthetic.png", mime="image/png")
    assert not list(tmp_path.iterdir())


def test_storage_write_failure_removes_partial_file(tmp_path, monkeypatch):
    """Ошибка после частичной записи не оставляет оригинал на диске."""
    original_fdopen = os.fdopen

    @contextmanager
    def failing_fdopen(descriptor, mode):
        with original_fdopen(descriptor, mode) as output:
            output.write(b"partial")
            raise OSError("synthetic failure")
            yield output  # pragma: no cover

    monkeypatch.setattr(storage.os, "fdopen", failing_fdopen)
    with pytest.raises(OSError, match="synthetic failure"):
        prepare(pdf_bytes(), tmp_path)
    assert not list(tmp_path.iterdir())


def test_storage_collision_preserves_existing_file(tmp_path, monkeypatch):
    """Эксклюзивное создание не перезаписывает существующий файл."""
    identifier = uuid4()
    monkeypatch.setattr(storage, "uuid4", lambda: identifier)
    existing = tmp_path / identifier.hex
    existing.write_bytes(b"existing synthetic")
    with pytest.raises(FileExistsError):
        prepare(pdf_bytes(), tmp_path)
    assert existing.read_bytes() == b"existing synthetic"
