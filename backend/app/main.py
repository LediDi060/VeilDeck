"""Точка входа FastAPI. Все роутеры регистрируются здесь один раз, дальше файл не трогаем."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from app.access.router import router as access_router
from app.api.health import router as health_router
from app.audit.router import router as audit_router
from app.auth.router import router as auth_router
from app.cards.router import router as cards_router
from app.catalog.router import router as catalog_router
from app.content.router import router as content_router
from app.core.config import get_settings
from app.core.database import Database
from app.core.errors import register_error_handlers
from app.core.request_id import RequestIdMiddleware
from app.grants.router import router as grants_router
from app.requests.router import router as requests_router
from app.review.router import router as review_router

API_PREFIX = "/api/v1"
STAFF_PREFIX = f"{API_PREFIX}/staff"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Создаёт и освобождает пул PostgreSQL и клиент Redis; DDL выполняет только Alembic."""
    settings = get_settings()
    database = Database(settings.database_url)
    redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    app.state.database = database
    app.state.redis = redis
    try:
        yield
    finally:
        await redis.aclose()
        await database.close()


def create_app() -> FastAPI:
    """Собирает приложение; без валидных секретов Settings() роняет процесс при старте."""
    settings = get_settings()
    app = FastAPI(
        title="VeilDeck API",
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)

    app.include_router(health_router)
    # Публичная зона
    app.include_router(catalog_router, prefix=f"{API_PREFIX}/cards")
    app.include_router(requests_router, prefix=f"{API_PREFIX}/cards")
    # Viewer
    app.include_router(access_router, prefix=f"{API_PREFIX}/access")
    app.include_router(content_router, prefix=f"{API_PREFIX}/access")
    # Staff
    app.include_router(auth_router, prefix=f"{STAFF_PREFIX}/auth")
    app.include_router(cards_router, prefix=f"{STAFF_PREFIX}/cards")
    app.include_router(review_router, prefix=f"{STAFF_PREFIX}/requests")
    app.include_router(grants_router, prefix=f"{STAFF_PREFIX}/grants")
    app.include_router(audit_router, prefix=f"{STAFF_PREFIX}/audit")
    return app


app = create_app()
