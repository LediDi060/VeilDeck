"""cards: бизнес-логика без FastAPI/HTTP; Principal и сессия БД приходят аргументами."""

from dataclasses import dataclass
from pathlib import Path

from app.cards.material_validation import MaterialMetadata, validate_material
from app.cards.storage import store_material
from app.core.exceptions import Forbidden
from app.core.principal import Principal, Role


@dataclass(frozen=True)
class PreparedMaterial:
    """Результат подготовки; не является записью materials или подтверждением загрузки."""

    storage_key: str
    metadata: MaterialMetadata


def prepare_material(
    principal: Principal, *, data: bytes, filename: str, declared_mime: str, storage_directory: Path
) -> PreparedMaterial:
    """Внутренний этап загрузки: проверка роли, валидация и запись вне веб-корня.

    Вызывающий код обязан получить Principal из серверной сессии и каталог из конфигурации.
    Перед HTTP-интеграцией нужны карточка, лимит файлов, транзакция БД и аудит отказов.
    """
    # Второй рубеж разделения обязанностей: T-07 / SR-16.
    if principal.role != Role.ADMIN:
        raise Forbidden
    metadata = validate_material(data, filename=filename, declared_mime=declared_mime)
    storage_key = store_material(data, storage_directory)
    return PreparedMaterial(storage_key=storage_key, metadata=metadata)
