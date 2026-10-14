"""Асинхронное подключение PostgreSQL; транзакцией управляет доменный сервис."""

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Общие метаданные ORM для Alembic; приложение не вызывает create_all."""


class Database:
    """Один пул на экземпляр приложения, отдельная сессия на запрос."""

    def __init__(self, url: str) -> None:
        self.engine = create_async_engine(url, pool_pre_ping=True, echo=False, hide_parameters=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def close(self) -> None:
        """Закрывает пул при остановке приложения."""
        await self.engine.dispose()
