"""Таймеры актора комнаты: реальные (asyncio) и тестовые (двигаются вручную с FakeClock)."""

from __future__ import annotations

import asyncio
import heapq
import itertools
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from app.core.clock import FakeClock
from app.core.logging import get_logger

TimerCallback = Callable[[], Awaitable[None]]

log = get_logger(__name__)


class TimerHandle(Protocol):
    def cancel(self) -> None: ...


class Timers(Protocol):
    def call_later(self, delay_ms: float, callback: TimerCallback) -> TimerHandle: ...


class _AsyncioHandle:
    def __init__(self) -> None:
        self.cancelled = False
        self.handle: asyncio.TimerHandle | None = None
        self.task: asyncio.Task[None] | None = None

    def cancel(self) -> None:
        self.cancelled = True
        if self.handle is not None:
            self.handle.cancel()


class AsyncioTimers:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    def call_later(self, delay_ms: float, callback: TimerCallback) -> TimerHandle:
        loop = asyncio.get_running_loop()
        h = _AsyncioHandle()

        def fire() -> None:
            if h.cancelled:
                return
            task = loop.create_task(self._run(callback))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        h.handle = loop.call_later(max(0.0, delay_ms) / 1000, fire)
        return h

    @staticmethod
    async def _run(callback: TimerCallback) -> None:
        try:
            await callback()
        except Exception:
            log.exception("timer_callback_failed")


@dataclass(order=True)
class _FakeTimer:
    due_ms: float
    seq: int
    callback: TimerCallback = field(compare=False)
    cancelled: bool = field(default=False, compare=False)

    def cancel(self) -> None:
        self.cancelled = True


class FakeTimers:
    """Детерминированные таймеры для тестов: `await advance(ms)` двигает FakeClock и вызывает
    просроченные колбэки строго по порядку."""

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self._elapsed = 0.0
        self._heap: list[_FakeTimer] = []
        self._seq = itertools.count()

    def call_later(self, delay_ms: float, callback: TimerCallback) -> TimerHandle:
        timer = _FakeTimer(self._elapsed + max(0.0, delay_ms), next(self._seq), callback)
        heapq.heappush(self._heap, timer)
        return timer

    @property
    def pending(self) -> int:
        return sum(1 for t in self._heap if not t.cancelled)

    async def advance(self, ms: float) -> None:
        target = self._elapsed + ms
        while self._heap and self._heap[0].due_ms <= target:
            timer = heapq.heappop(self._heap)
            if timer.cancelled:
                continue
            self.clock.advance(timer.due_ms - self._elapsed)
            self._elapsed = timer.due_ms
            await timer.callback()
        self.clock.advance(target - self._elapsed)
        self._elapsed = target
