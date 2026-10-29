"""Доменные ошибки с машинным кодом и человекочитаемым текстом для пользователя."""

from __future__ import annotations


class AppError(Exception):
    code: str = "internal"
    status_code: int = 500
    default_message: str = "Что-то пошло не так. Попробуйте ещё раз."

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        self.message = message or self.default_message
        if code is not None:
            self.code = code
        super().__init__(self.message)


class NotFoundError(AppError):
    code = "not_found"
    status_code = 404
    default_message = "Не найдено."


class ForbiddenError(AppError):
    code = "forbidden"
    status_code = 403
    default_message = "Недостаточно прав."


class UnauthorizedError(AppError):
    code = "unauthorized"
    status_code = 401
    default_message = "Нужно войти."


class ValidationError(AppError):
    code = "validation"
    status_code = 422
    default_message = "Некорректный запрос."


class RateLimitedError(AppError):
    code = "rate_limited"
    status_code = 429
    default_message = "Слишком много действий подряд — подождите секунду."


class ConflictError(AppError):
    """Команда устарела: состояние уже изменилось (двойной «следующий» и т.п.)."""

    code = "stale"
    status_code = 409
    default_message = "Кто-то успел раньше — состояние уже обновилось."
