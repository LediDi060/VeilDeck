"""Минимальный аудит отказов каталога с allowlist и hash-цепочкой."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit import repository

EVENT_FIELDS = (
    "ts",
    "actor_type",
    "actor_ref",
    "action",
    "object_type",
    "object_id",
    "outcome",
    "ip_hash",
    "request_id",
    "details",
)


def event_hash(previous: str, values: dict) -> str:
    """Хеширует предыдущий hash и канонический JSON; id — порядковый ключ вне payload."""
    payload = {key: values[key] for key in EVENT_FIELDS}
    payload["ts"] = payload["ts"].astimezone(UTC).isoformat()
    payload["request_id"] = str(payload["request_id"])
    payload["object_id"] = str(payload["object_id"]) if payload["object_id"] else None
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256((previous + canonical).encode()).hexdigest()


async def record_catalog_limit(
    sessions: async_sessionmaker[AsyncSession],
    *,
    ip_hash: str,
    request_id: str,
) -> None:
    """Пишет отказ отдельной транзакцией, без IP, query string и confidential-данных."""
    values = {
        "ts": datetime.now(UTC),
        "actor_type": "anonymous",
        "actor_ref": "anonymous",
        "action": "catalog.rate_limited",
        "object_type": "catalog",
        "object_id": None,
        "outcome": "deny",
        "ip_hash": ip_hash,
        "request_id": UUID(request_id),
        "details": {"limit": 60, "window_seconds": 60},
    }
    async with sessions() as session, session.begin():
        previous = await repository.lock_chain(session)
        await repository.append(session, {**values, "prev_hash": previous, "hash": event_hash(previous, values)})


async def verify_chain(session: AsyncSession) -> bool:
    """Внутренняя проверка hash-цепочки; HTTP-доступ к аудиту остаётся задачей 8.1."""
    previous = "0" * 64
    for event in await repository.read_chain(session):
        values = {key: getattr(event, key) for key in EVENT_FIELDS}
        if event.prev_hash != previous or event.hash != event_hash(previous, values):
            return False
        previous = event.hash
    return True
