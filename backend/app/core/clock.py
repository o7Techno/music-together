"""Источник времени. Внедряется в доменную логику, чтобы тестировать её без реального времени."""

from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def now_ms(self) -> int:
        """Серверное время протокола: epoch, миллисекунды."""
        ...

    def monotonic(self) -> float:
        """Монотонные секунды для интервалов и таймеров."""
        ...


class SystemClock:
    def now_ms(self) -> int:
        return time.time_ns() // 1_000_000

    def monotonic(self) -> float:
        return time.monotonic()


class FakeClock:
    """Ручные часы для тестов: время двигается только через `advance`."""

    def __init__(self, start_ms: int = 1_700_000_000_000) -> None:
        self._now_ms = start_ms
        self._mono = 1000.0

    def now_ms(self) -> int:
        return self._now_ms

    def monotonic(self) -> float:
        return self._mono

    def advance(self, ms: float) -> None:
        self._now_ms += round(ms)
        self._mono += ms / 1000
