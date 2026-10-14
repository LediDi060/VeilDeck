"""Строгие публичные контракты каталога (SR-02, SR-03)."""

from datetime import datetime

from pydantic import UUID4, BaseModel, ConfigDict, Field

from app.core.card_fields import DealType, Industry, RegionMacro, RevenueBand, SizeBand


class CatalogQuery(BaseModel):
    """Только обобщённые фильтры, без confidential-параметров."""

    model_config = ConfigDict(extra="forbid")
    page: int = Field(default=1, ge=1, le=100_000)
    page_size: int = Field(default=20, ge=1, le=20)
    industry: Industry | None = None
    region_macro: RegionMacro | None = None
    deal_type: DealType | None = None


class TeaserCard(BaseModel):
    """Allowlist публичных полей; закрытых данных нет даже в SQL-проекции (T-02)."""

    model_config = ConfigDict(extra="forbid")
    id: UUID4
    title_generic: str
    industry: Industry
    region_macro: RegionMacro
    size_band: SizeBand
    revenue_band: RevenueBand
    deal_type: DealType
    teaser_text: str
    published_at: datetime


class CatalogPage(BaseModel):
    """Количество относится только к опубликованным карточкам."""

    model_config = ConfigDict(extra="forbid")
    items: list[TeaserCard]
    page: int
    page_size: int
    total: int
