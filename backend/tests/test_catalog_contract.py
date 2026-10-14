"""Контракты REST без инфраструктуры; сквозные проверки — test_catalog_postgres.py."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import catalog_limit
from app.api.catalog_limit import limit_catalog
from app.audit.service import event_hash
from app.core.config import get_settings
from app.main import create_app


@pytest.fixture
def contract_client():
    """Отключает только лимитер в тесте валидации; SQL для невалидного запроса не выполняется."""
    app = create_app()
    app.dependency_overrides[limit_catalog] = lambda: None
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "page_size=0",
        "page_size=21",
        "page=100001",
        "industry=unknown",
        "region_macro=city",
        "deal_type=unknown",
        "org_name=Synthetic",
    ],
)
def test_tc_cat_invalid_query_rejected(contract_client, query):
    """TC-CAT-03: неизвестные и слишком узкие параметры не попадают в SQL."""
    response = contract_client.get("/api/v1/cards?" + query)
    assert response.status_code == 422
    assert set(response.json()["error"]) == {"code", "message", "request_id"}


@pytest.mark.parametrize("identifier", ["123", "not-uuid", "00000000-0000-1000-8000-000000000001"])
def test_tc_cat_invalid_id_is_404(contract_client, identifier):
    """Невалидные/не-v4 ID получают такой же безопасный 404."""
    response = contract_client.get("/api/v1/cards/" + identifier)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_audit_hash_is_canonical_and_detects_change():
    """Порядок ключей JSON не меняет hash; изменение значения меняет hash."""
    event = {
        "ts": datetime(2026, 10, 1, tzinfo=UTC),
        "actor_type": "anonymous",
        "actor_ref": "anonymous",
        "action": "catalog.rate_limited",
        "object_type": "catalog",
        "object_id": None,
        "outcome": "deny",
        "ip_hash": "a" * 64,
        "request_id": uuid4(),
        "details": {"limit": 60, "window_seconds": 60},
    }
    first = event_hash("0" * 64, event)
    assert event_hash("0" * 64, dict(reversed(list(event.items())))) == first
    assert event_hash("0" * 64, {**event, "outcome": "allow"}) != first
    assert event_hash("1" * 64, event) != first


def test_database_connection_failure_is_safe_503(monkeypatch):
    """Ошибка первого TCP-подключения не раскрывает драйвер, DSN или секреты."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:1/test")
    get_settings.cache_clear()
    try:
        app = create_app()
        app.dependency_overrides[limit_catalog] = lambda: None
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/v1/cards")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "service_unavailable"
        assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
        assert response.json()["error"]["request_id"] != "-"
        assert "asyncpg" not in response.text
        assert "127.0.0.1" not in response.text
    finally:
        get_settings.cache_clear()


def test_audit_database_failure_is_safe_503_and_releases_reservation(monkeypatch):
    """Первое подключение audit-БД не даёт 500 и не блокирует повторную запись аудита."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:1/test")
    monkeypatch.setattr(catalog_limit, "check_catalog", AsyncMock(return_value=(60, "reservation")))
    release = AsyncMock()
    monkeypatch.setattr(catalog_limit, "release_catalog_audit", release)
    get_settings.cache_clear()
    try:
        with TestClient(create_app(), raise_server_exceptions=False) as client:
            response = client.get("/api/v1/cards")
        assert response.status_code == 503
        assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
        assert response.json()["error"]["request_id"] != "-"
        release.assert_awaited_once()
        assert release.await_args.args[2] == "reservation"
    finally:
        get_settings.cache_clear()
