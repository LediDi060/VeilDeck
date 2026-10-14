"""Зависимость сессии: SQL и границы транзакций остаются в доменах."""

from collections.abc import AsyncIterator

from asyncpg import PostgresError
from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceUnavailable


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Выдаёт одну сессию и гарантирует её закрытие, включая откат при ошибке."""
    try:
        async with request.app.state.database.sessions() as session:
            yield session
    except (OSError, SQLAlchemyError, PostgresError):
        # Ошибки первичного TCP-подключения asyncpg могут не оборачиваться SQLAlchemy.
        raise ServiceUnavailable from None
