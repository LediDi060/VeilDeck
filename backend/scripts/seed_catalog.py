"""Повторяемое заполнение только синтетических карточек (часть 4.4)."""

import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert

from app.cards.leak_linter import find_leaks
from app.cards.models import Card
from app.core.database import Database

SEED_IDS = (
    UUID("d39a2aed-6ae6-4f40-80a5-e0d60d0591e0"),
    UUID("55738666-4114-466d-a3ac-fb1fc5e84d18"),
    UUID("a85e109c-4a05-43c1-aae5-8b088c1c28cf"),
    UUID("89b2215e-25bd-4ec4-9ffb-c2f8005798a2"),
    UUID("f69ca296-7f91-4251-a64d-391b04e7bb68"),
    UUID("ed221d30-3d6a-48de-ab60-28c0ab0f14ab"),
    UUID("83619abb-ef58-4407-9754-bd46c7c51455"),
    UUID("86cd7080-e221-412c-bff5-f6d302143774"),
    UUID("63503e31-ee8b-4a92-a392-3f308a22bad0"),
    UUID("02ea9ad9-e084-49b6-b846-b3b4fd0627a3"),
    UUID("f263859c-df68-4a58-9d62-cba62f54fccf"),
    UUID("02332073-7731-4a1b-827d-f3a1b616edd6"),
    UUID("57dffa1e-f28c-4fdb-915a-28d7e06b7db4"),
    UUID("0f63f80c-c849-412c-b06a-eb8e7f66018a"),
)


def synthetic_cards() -> list[dict]:
    """Создаёт 12 опубликованных карточек, черновик и архив со стабильными UUIDv4."""
    rows = []
    for index, identifier in enumerate(SEED_IDS, start=1):
        status = "published" if index <= 12 else ("draft" if index == 13 else "archived")
        values = {
            "id": identifier,
            "status": status,
            "title_generic": f"Синтетическая корпоративная возможность {index}",
            "industry": "manufacturing" if index % 2 else "logistics",
            "region_macro": "europe" if index % 3 else "asia",
            "size_band": "50_to_249",
            "revenue_band": "10m_to_50m",
            "deal_type": "equity" if index % 2 else "partnership",
            "teaser_text": "SYNTHETIC — FOR TESTING ONLY. Обезличенное предложение для учебной демонстрации.",
            "org_name": f"Asterion Logistik GmbH {index}",
            "org_aliases": [],
            "full_description": "SYNTHETIC — закрытое демонстрационное описание.",
            "created_by": None,
            "published_at": datetime(2026, 10, 1, tzinfo=UTC) if status == "published" else None,
        }
        fields = {name: values[name] for name in ("title_generic", "teaser_text")}
        if find_leaks(fields, values["org_name"], values["org_aliases"]):
            raise RuntimeError("синтетический teaser не прошёл линтер")
        rows.append(values)
    return rows


async def seed() -> None:
    """Добавляет отсутствующие demo-записи, не меняя существующие данные."""
    database = Database(os.environ["MIGRATION_DATABASE_URL"])
    try:
        async with database.sessions() as session, session.begin():
            await session.execute(insert(Card).values(synthetic_cards()).on_conflict_do_nothing(index_elements=["id"]))
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(seed())
    print("Синтетический каталог подготовлен: 12 published, 1 draft, 1 archived (повтор без дублей).")
