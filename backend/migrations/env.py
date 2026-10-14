"""Миграции выполняет только app_owner, URL поступает из окружения."""

import asyncio
import os

from alembic import context
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.audit.models import AuditEvent  # noqa: F401
from app.cards.models import Card  # noqa: F401
from app.core.database import Base

target_metadata = Base.metadata


def configure(connection):
    """Проверяет роль и применяет миграцию в транзакции."""
    if connection.scalar(text("SELECT current_user")) != "app_owner":
        raise RuntimeError("миграции требуют роль app_owner")
    connection.commit()
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_online():
    """Создаёт отдельный пул миграций, недоступный приложению."""
    engine = create_async_engine(os.environ["MIGRATION_DATABASE_URL"], hide_parameters=True)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(configure)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(url=os.environ["MIGRATION_DATABASE_URL"], target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())
