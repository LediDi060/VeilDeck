"""catalog: читает только собственное представление, без commit."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import catalog_cards
from app.catalog.schemas import CatalogQuery


async def list_cards(session: AsyncSession, query: CatalogQuery) -> tuple[list[dict], int]:
    """Применяет фильтры, стабильную сортировку и ограниченный LIMIT."""
    conditions = [
        catalog_cards.c[name] == value
        for name in ("industry", "region_macro", "deal_type")
        if (value := getattr(query, name)) is not None
    ]
    total = await session.scalar(select(func.count()).select_from(catalog_cards).where(*conditions))
    result = await session.execute(
        select(catalog_cards)
        .where(*conditions)
        .order_by(catalog_cards.c.published_at.desc(), catalog_cards.c.id)
        .offset((query.page - 1) * query.page_size)
        .limit(query.page_size)
    )
    return [dict(row) for row in result.mappings()], total or 0


async def get_card(session: AsyncSession, card_id: UUID) -> dict | None:
    """Черновые и архивные карточки отсутствуют в публичном представлении."""
    result = await session.execute(select(catalog_cards).where(catalog_cards.c.id == card_id))
    row = result.mappings().one_or_none()
    return dict(row) if row else None
