"""Полная карточка; публичный API читает отдельную SQL-проекцию."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Card(Base):
    """Синтетическая карточка корпоративной возможности."""

    __tablename__ = "cards"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published', 'archived')", name="card_status"),
        CheckConstraint("industry IN ('manufacturing', 'logistics', 'technology', 'services')", name="card_industry"),
        CheckConstraint("region_macro IN ('europe', 'asia', 'middle_east', 'other')", name="card_region"),
        CheckConstraint("size_band IN ('under_50', '50_to_249', '250_plus')", name="card_size"),
        CheckConstraint("revenue_band IN ('under_10m', '10m_to_50m', '50m_plus')", name="card_revenue"),
        CheckConstraint("deal_type IN ('equity', 'asset', 'partnership')", name="card_deal"),
        CheckConstraint("status != 'published' OR published_at IS NOT NULL", name="card_published_at"),
        CheckConstraint("char_length(title_generic) BETWEEN 1 AND 80", name="card_title_length"),
        CheckConstraint("char_length(teaser_text) <= 600", name="card_teaser_length"),
        Index("ix_cards_catalog", "status", "published_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    title_generic: Mapped[str] = mapped_column(String(80))
    industry: Mapped[str] = mapped_column(String(32))
    region_macro: Mapped[str] = mapped_column(String(32))
    size_band: Mapped[str] = mapped_column(String(32))
    revenue_band: Mapped[str] = mapped_column(String(32))
    deal_type: Mapped[str] = mapped_column(String(32))
    teaser_text: Mapped[str] = mapped_column(String(600))
    org_name: Mapped[str] = mapped_column(String(200))
    org_aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    full_description: Mapped[str] = mapped_column(Text)
    created_by: Mapped[UUID | None]
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
