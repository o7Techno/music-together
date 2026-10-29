"""Token bucket — ограничение частоты команд/запросов на ключ (пользователя)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    updated: float


class RateLimiter:
    """`rate` токенов в секунду, ёмкость `burst`. Ключи без активности удаляются при `prune`."""

    def __init__(self, rate: float, burst: float, monotonic: Callable[[], float]) -> None:
        self.rate = rate
        self.burst = burst
        self._monotonic = monotonic
        self._buckets: dict[str, _Bucket] = {}

    def allow(self, key: str, cost: float = 1.0) -> bool:
        now = self._monotonic()
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = self._buckets[key] = _Bucket(self.burst, now)
        bucket.tokens = min(self.burst, bucket.tokens + (now - bucket.updated) * self.rate)
        bucket.updated = now
        if bucket.tokens >= cost:
            bucket.tokens -= cost
            return True
        return False

    def prune(self, idle_seconds: float = 600) -> None:
        now = self._monotonic()
        stale = [k for k, b in self._buckets.items() if now - b.updated > idle_seconds]
        for key in stale:
            del self._buckets[key]
