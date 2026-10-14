"""Перевод исключений в HTTP: единый формат {"error": {"code", "message", "request_id"}} без стек-трейсов."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import (
    Conflict,
    DomainError,
    Forbidden,
    Gone,
    NotFound,
    RateLimited,
    ServiceUnavailable,
    Unauthorized,
)
from app.core.request_id import get_request_id

HTTP_INTERNAL_ERROR = 500
VALIDATION_STATUS = 422
STATUS_BY_ERROR: dict[type[DomainError], int] = {
    Unauthorized: 401,
    Forbidden: 403,
    NotFound: 404,
    Conflict: 409,
    Gone: 410,
    RateLimited: 429,
    ServiceUnavailable: 503,
}


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """Собирает ответ об ошибке в едином формате."""
    body = {"error": {"code": code, "message": message, "request_id": get_request_id()}}
    return JSONResponse(status_code=status_code, content=body)


def register_error_handlers(app: FastAPI) -> None:
    """Подключает обработчики, скрывающие внутренние детали."""

    @app.exception_handler(SQLAlchemyError)
    async def _database_error(_: Request, __: SQLAlchemyError) -> JSONResponse:
        return error_response(503, ServiceUnavailable.code, ServiceUnavailable.message)

    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        status = STATUS_BY_ERROR.get(type(exc), HTTP_INTERNAL_ERROR)
        response = error_response(status, exc.code, exc.message)
        if isinstance(exc, RateLimited):
            response.headers["Retry-After"] = str(exc.retry_after)
        return response

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(exc.status_code, f"http_{exc.status_code}", "Ошибка запроса")

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
        return error_response(VALIDATION_STATUS, "validation_error", "Некорректные данные запроса")

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, __: Exception) -> JSONResponse:
        return error_response(HTTP_INTERNAL_ERROR, "internal_error", "Внутренняя ошибка")
