"""Append-only события без чувствительного содержимого (SR-26, SR-27)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Identity, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditEvent(Base):
    """Запись hash-цепочки; изменений существующих записей в приложении нет."""

    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_type: Mapped[str] = mapped_column(String(32))
    actor_ref: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64))
    object_type: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[UUID | None]
    outcome: Mapped[str] = mapped_column(String(16))
    ip_hash: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[UUID]
    details: Mapped[dict] = mapped_column(JSONB)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
