"""Публичный REST-каталог: только обезличенная SQL-проекция."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.catalog_limit import limit_catalog
from app.api.database import get_session
from app.catalog import service
from app.catalog.schemas import CatalogPage, CatalogQuery, TeaserCard

router = APIRouter(tags=["catalog"], dependencies=[Depends(limit_catalog)])


@router.get("", response_model=CatalogPage, operation_id="listCatalogCards")
async def list_cards(
    query: Annotated[CatalogQuery, Query()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CatalogPage:
    """Список опубликованных карточек: фильтры enum и не более 20 записей на страницу."""
    return await service.list_cards(session, query)


@router.get("/{card_id}", response_model=TeaserCard, operation_id="getCatalogCard")
async def get_card(card_id: str, session: Annotated[AsyncSession, Depends(get_session)]) -> TeaserCard:
    """Одинаковый 404 для неверного UUID, черновика, архива и отсутствующей карточки."""
    return await service.get_card(session, card_id)
