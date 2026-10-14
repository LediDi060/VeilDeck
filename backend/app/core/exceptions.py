"""Доменные исключения без привязки к HTTP: в коды ответов их переводит только обработчик в core/errors.py."""


class DomainError(Exception):
    """Базовая ошибка домена; code — стабильный машинный код для клиента."""

    code = "domain_error"
    message = "Ошибка"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.message
        super().__init__(self.message)


class ServiceUnavailable(DomainError):
    """БД или лимитер недоступны; детали подключения не раскрываются."""

    code = "service_unavailable"
    message = "Сервис временно недоступен"


class NotFound(DomainError):
    """Объекта нет ИЛИ он чужой: тело ответа одинаково (SR, T-03)."""

    code = "not_found"
    message = "Не найдено"


class Unauthorized(DomainError):
    """Нет валидной сессии."""

    code = "unauthorized"
    message = "Требуется вход"


class Forbidden(DomainError):
    """Роль не допускает действие (разделение обязанностей)."""

    code = "forbidden"
    message = "Недостаточно прав"


class Conflict(DomainError):
    """Повторное действие, нарушение уникальности (например, второе решение по запросу)."""

    code = "conflict"
    message = "Конфликт состояния"


class Gone(DomainError):
    """Ссылка использована, истекла или отозвана."""

    code = "gone"
    message = "Ресурс недоступен"


class RateLimited(DomainError):
    """Превышен лимит запросов."""

    code = "rate_limited"
    message = "Слишком много запросов"

    def __init__(self, retry_after: int = 60) -> None:
        self.retry_after = retry_after
        super().__init__()
