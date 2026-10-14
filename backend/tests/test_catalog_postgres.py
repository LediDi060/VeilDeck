"""Интеграция реального PostgreSQL 16 + Redis; выполняется также в CI."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.audit.service import verify_chain
from app.core.config import get_settings
from app.core.database import Database
from app.main import create_app
from scripts.seed_catalog import SEED_IDS

REQUIRED = ("TEST_DATABASE_OWNER_URL", "TEST_APP_RW_PASSWORD", "TEST_REDIS_URL")
pytestmark = pytest.mark.skipif(
    not all(os.getenv(key) for key in REQUIRED),
    reason="нужны отдельные PostgreSQL/Redis из TEST_*",
)
BACKEND = Path(__file__).resolve().parents[1]


def run_script(module):
    """Запускает доверенную CLI-команду с owner URL; секреты не выводятся."""
    environment = {
        **os.environ,
        "MIGRATION_DATABASE_URL": os.environ["TEST_DATABASE_OWNER_URL"],
        "APP_RW_PASSWORD": os.environ["TEST_APP_RW_PASSWORD"],
    }
    subprocess.run([sys.executable, "-m", module], env=environment, cwd=BACKEND, check=True, capture_output=True)  # noqa: S603 — только модули из тестового кода


async def sql(url, query):
    """Выполняет SQL в отдельном пуле, не перенося соединение между event loop."""
    engine = create_async_engine(url, hide_parameters=True)
    try:
        async with engine.begin() as connection:
            result = await connection.execute(text(query))
            return result.fetchall() if result.returns_rows else []
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def database_url():
    """Мигрирует только выделенную БД *_test и повторно запускает seed."""
    owner = make_url(os.environ["TEST_DATABASE_OWNER_URL"])
    assert owner.database.endswith("_test"), "интеграционные тесты требуют отдельную БД *_test"
    run_script("scripts.bootstrap_db")
    run_script("scripts.seed_catalog")
    run_script("scripts.seed_catalog")
    return owner.set(username="app_rw", password=os.environ["TEST_APP_RW_PASSWORD"]).render_as_string(
        hide_password=False
    )


@pytest.fixture
def api(database_url, monkeypatch):
    """Поднимает настоящее приложение с app_rw и настоящим Redis."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("REDIS_URL", os.environ["TEST_REDIS_URL"])
    get_settings.cache_clear()

    async def reset_redis():
        redis = Redis.from_url(os.environ["TEST_REDIS_URL"])
        assert redis.connection_pool.connection_kwargs["db"] == 15
        await redis.flushdb()
        await redis.aclose()

    asyncio.run(reset_redis())
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client
    get_settings.cache_clear()


def test_tc_cat_list_filters_and_projection(api):
    """Таблица сохраняет confidential-поля, а SQL view и HTTP их исключают."""
    response = api.get("/api/v1/cards")
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["total"] == 12
    assert len(page["items"]) == 12
    fields = {
        "id",
        "title_generic",
        "industry",
        "region_macro",
        "size_band",
        "revenue_band",
        "deal_type",
        "teaser_text",
        "published_at",
    }
    assert all(set(card) == fields for card in page["items"])
    assert "Asterion" not in response.text
    assert "закрытое демонстрационное описание" not in response.text
    filtered = api.get("/api/v1/cards?industry=manufacturing&region_macro=asia&deal_type=equity").json()
    assert filtered["total"] == 2
    first = api.get("/api/v1/cards?page_size=5").json()
    second = api.get("/api/v1/cards?page_size=5&page=2").json()
    assert len(first["items"]) == len(second["items"]) == 5
    assert not {card["id"] for card in first["items"]} & {card["id"] for card in second["items"]}
    identifier = first["items"][0]["id"]
    assert api.get("/api/v1/cards/" + identifier).json() == first["items"][0]


def test_tc_cat_draft_archive_missing_same_error(api):
    """TC-CAT-02: одинаковый 404, включая невалидный UUID (request_id всегда новый)."""
    identifiers = [str(uuid4()), "123", str(SEED_IDS[12]), str(SEED_IDS[13])]
    errors = []
    for identifier in identifiers:
        response = api.get("/api/v1/cards/" + identifier)
        assert response.status_code == 404
        errors.append({k: v for k, v in response.json()["error"].items() if k != "request_id"})
    assert all(error == errors[0] for error in errors)


def test_tc_rl_response_and_append_only_audit(api, database_url):
    """TC-RL-01/TC-AUD-02: 429, Retry-After, одно событие, закрытые права и hash-цепочка."""
    owner = os.environ["TEST_DATABASE_OWNER_URL"]
    before = asyncio.run(sql(owner, "SELECT count(*) FROM audit_events"))[0][0]
    for _ in range(60):
        assert api.get("/api/v1/cards").status_code == 200
    response = api.get("/api/v1/cards", headers={"X-Forwarded-For": "203.0.113.9"})
    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= 60
    assert api.get("/api/v1/cards").status_code == 429
    after = asyncio.run(sql(owner, "SELECT count(*) FROM audit_events"))[0][0]
    assert after == before + 1
    for query in [
        "SELECT org_name FROM cards",
        "DELETE FROM audit_events",
        "UPDATE audit_events SET outcome='allow'",
        "TRUNCATE audit_events",
    ]:
        with pytest.raises(DBAPIError):
            asyncio.run(sql(database_url, query))
    # Триггер защищает и владельца от обычного DML, не только app_rw.
    with pytest.raises(DBAPIError):
        asyncio.run(sql(owner, "DELETE FROM audit_events"))

    async def verify():
        database = Database(database_url)
        try:
            async with database.sessions() as session:
                return await verify_chain(session)
        finally:
            await database.close()

    assert asyncio.run(verify())


def test_persistence_across_application_restart(api, database_url):
    """Новый процесс приложения читает те же строки; seed не создаёт дублей."""
    assert api.get("/api/v1/cards").json()["total"] == 12
    assert asyncio.run(sql(database_url, "SELECT count(*) FROM catalog_cards"))[0][0] == 12
    assert asyncio.run(sql(os.environ["TEST_DATABASE_OWNER_URL"], "SELECT count(*) FROM cards"))[0][0] == 14


def test_migration_roundtrip(database_url):
    """На отдельной тестовой БД downgrade/upgrade восстанавливают view, таблицы и права."""
    environment = {**os.environ, "MIGRATION_DATABASE_URL": os.environ["TEST_DATABASE_OWNER_URL"]}
    for arguments in [("downgrade", "base"), ("upgrade", "head")]:
        subprocess.run(  # noqa: S603 — фиксированные команды Alembic
            [sys.executable, "-m", "alembic", *arguments],
            cwd=BACKEND,
            env=environment,
            check=True,
            capture_output=True,
        )
    run_script("scripts.seed_catalog")
    assert asyncio.run(sql(database_url, "SELECT count(*) FROM catalog_cards"))[0][0] == 12
