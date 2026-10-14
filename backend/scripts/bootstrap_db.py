"""Первичная подготовка app_rw и миграции от app_owner; секреты не выводятся."""

import asyncio
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine


async def prepare_role() -> None:
    """Создаёт ограниченную роль; пароль передаётся через параметризованный PostgreSQL format."""
    password = os.environ["APP_RW_PASSWORD"]
    if len(password) < 32:
        raise ValueError("APP_RW_PASSWORD должен содержать не менее 32 символов")
    engine = create_async_engine(os.environ["MIGRATION_DATABASE_URL"], hide_parameters=True)
    try:
        async with engine.begin() as connection:
            if await connection.scalar(text("SELECT current_user")) != "app_owner":
                raise RuntimeError("подготовка требует роль app_owner")
            exists = await connection.scalar(text("SELECT EXISTS(SELECT FROM pg_roles WHERE rolname='app_rw')"))
            if not exists:
                await connection.execute(
                    text("CREATE ROLE app_rw LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION")
                )
            # Имя роли фиксировано; сервер экранирует пароль как SQL-литерал (%L).
            statement = await connection.scalar(
                text("SELECT format('ALTER ROLE app_rw PASSWORD %L', CAST(:password AS text))"),
                {"password": password},
            )
            await connection.exec_driver_sql(statement)
    except SQLAlchemyError:
        # В SQL ALTER ROLE присутствует пароль: исходное исключение не показываем.
        raise RuntimeError("не удалось подготовить роль приложения") from None
    finally:
        await engine.dispose()


def main() -> None:
    """Запускается однократно до API; повторное выполнение безопасно."""
    asyncio.run(prepare_role())
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    print("База подготовлена; миграции применены.")


if __name__ == "__main__":
    main()
