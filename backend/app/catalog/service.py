"""catalog: бизнес-логика без HTTP, транзакцией управляет сервис."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import repository
from app.catalog.schemas import CatalogPage, CatalogQuery, TeaserCard
from app.core.exceptions import NotFound


async def list_cards(session: AsyncSession, query: CatalogQuery) -> CatalogPage:
    """Возвращает только проверенную публичную схему."""
    async with session.begin():
        items, total = await repository.list_cards(session, query)
    return CatalogPage(
        items=[TeaserCard.model_validate(row) for row in items],
        total=total,
        page=query.page,
        page_size=query.page_size,
    )


async def get_card(session: AsyncSession, card_id: str) -> TeaserCard:
    """Неверный, отсутствующий или непубличный ID даёт NotFound (T-03 / SR-11)."""
    try:
        identifier = UUID(card_id)
    except ValueError:
        raise NotFound from None
    if identifier.version != 4:
        raise NotFound
    async with session.begin():
        row = await repository.get_card(session, identifier)
    if row is None:
        raise NotFound
    return TeaserCard.model_validate(row)
