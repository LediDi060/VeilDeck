"""audit: только собственная таблица, без commit."""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent

AUDIT_LOCK = 7146026


async def lock_chain(session: AsyncSession) -> str:
    """Сериализует дописывание цепочки до конца транзакции (T-13 / SR-27)."""
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": AUDIT_LOCK})
    previous = await session.scalar(select(AuditEvent.hash).order_by(AuditEvent.id.desc()).limit(1))
    return previous or "0" * 64


async def append(session: AsyncSession, values: dict) -> None:
    """Вставляет одно событие; транзакция принадлежит сервису."""
    session.add(AuditEvent(**values))
    await session.flush()


async def read_chain(session: AsyncSession) -> list[AuditEvent]:
    """Читает события в порядке добавления для проверки целостности."""
    return list((await session.scalars(select(AuditEvent).order_by(AuditEvent.id))).all())
