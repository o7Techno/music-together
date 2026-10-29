"""Структурированное логирование (structlog). Секреты маскируются процессором."""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

_SECRET_KEYS = re.compile(r"token|secret|password|authorization|cookie|key", re.IGNORECASE)
# Яндекс OAuth-токены: префикс y0_ / AQAAAA..., плюс любые Bearer-заголовки.
_SECRET_VALUES = re.compile(r"(y0_[A-Za-z0-9_\-]{20,}|AQAAAA[A-Za-z0-9_\-]{20,}|Bearer\s+\S+)")


def _mask(value: Any) -> Any:
    if isinstance(value, str):
        return _SECRET_VALUES.sub("***", value)
    return value


def mask_secrets(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict.keys()):
        if _SECRET_KEYS.search(key) and key != "event":
            event_dict[key] = "***"
        else:
            event_dict[key] = _mask(event_dict[key])
    return event_dict


def configure_logging(level: str = "INFO", *, json: bool = False) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())
    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            mask_secrets,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
