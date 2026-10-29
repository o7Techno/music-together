"""Проверка конфигурации при старте и необязательный Sentry (SPEC §7.7)."""

from __future__ import annotations

import re
from typing import Any

from app.core.config import MusicProviderKind, Settings
from app.core.logging import get_logger

log = get_logger(__name__)

_DEFAULT_SECRET = "dev-insecure-session-secret-change-me"  # noqa: S105 — маркер дефолта, не секрет
_TOKEN_LIKE = re.compile(r"(y0_[A-Za-z0-9_\-]{20,}|AQAAAA[A-Za-z0-9_\-]{20,}|Bearer\s+\S+)")


def validate_settings(settings: Settings) -> list[str]:
    """Ошибки конфигурации, с которыми нельзя запускаться в проде."""
    problems: list[str] = []
    if not settings.is_prod:
        return problems
    secret = settings.session_secret.get_secret_value()
    if secret == _DEFAULT_SECRET or len(secret) < 32:
        problems.append("SESSION_SECRET не задан или короче 32 символов")
    if not settings.public_origin.startswith("https://"):
        problems.append("PUBLIC_ORIGIN в проде должен начинаться с https://")
    if (
        settings.music_provider is MusicProviderKind.YANDEX
        and not settings.token_encryption_keys.get_secret_value()
    ):
        problems.append("MUSIC_PROVIDER=yandex требует TOKEN_ENCRYPTION_KEYS")
    return problems


def _scrub(event: Any, _hint: Any) -> Any:
    """Последний рубеж: никаких токенов и cookie в событиях Sentry."""
    request = event.get("request") or {}
    for key in ("cookies", "data"):
        request.pop(key, None)
    headers = request.get("headers") or {}
    for header in list(headers):
        if header.lower() in ("cookie", "authorization", "set-cookie"):
            headers[header] = "***"
    text = str(event.get("message") or "")
    if text:
        event["message"] = _TOKEN_LIKE.sub("***", text)
    return event


def init_sentry(settings: Settings) -> bool:
    if not settings.sentry_dsn:
        return False
    import sentry_sdk  # noqa: PLC0415 — импорт только при включённом Sentry

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env.value,
        traces_sample_rate=0.0,
        send_default_pii=False,
        before_send=_scrub,
    )
    log.info("sentry_enabled")
    return True
