"""Общий enum-контракт карточек и публичной проекции (SR-03, SR-18)."""

from enum import StrEnum


class CardStatus(StrEnum):
    """Состояния жизненного цикла."""

    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Industry(StrEnum):
    """Обобщённые отрасли."""

    MANUFACTURING = "manufacturing"
    LOGISTICS = "logistics"
    TECHNOLOGY = "technology"
    SERVICES = "services"


class RegionMacro(StrEnum):
    """Макрорегионы без адреса или города."""

    EUROPE = "europe"
    ASIA = "asia"
    MIDDLE_EAST = "middle_east"
    OTHER = "other"


class SizeBand(StrEnum):
    """Диапазоны численности сотрудников."""

    SMALL = "under_50"
    MEDIUM = "50_to_249"
    LARGE = "250_plus"


class RevenueBand(StrEnum):
    """Обобщённые диапазоны годовой выручки в EUR."""

    SMALL = "under_10m"
    MEDIUM = "10m_to_50m"
    LARGE = "50m_plus"


class DealType(StrEnum):
    """Типы корпоративных возможностей."""

    EQUITY = "equity"
    ASSET = "asset"
    PARTNERSHIP = "partnership"
