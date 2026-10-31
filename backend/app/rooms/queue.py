"""Очередь комнаты: текущий элемент, предстоящие, история (SPEC §4.3). Чистая логика без I/O."""

from __future__ import annotations

import random
import secrets
from collections import deque
from enum import StrEnum
from typing import Literal

from app.core.errors import NotFoundError, ValidationError
from app.core.schema import ApiModel
from app.providers.base import Track

HISTORY_LIMIT = 50
QUEUE_LIMIT = 2000


class RepeatMode(StrEnum):
    OFF = "off"
    QUEUE = "queue"
    TRACK = "track"


class QueueOrigin(ApiModel):
    """Откуда элемент: добавлен вручную или пришёл из волны. Для подписи в плеере и списках."""

    kind: Literal["manual", "wave"] = "manual"
    owner_id: str | None = None
    owner_name: str | None = None
    seed_label: str | None = None
    shared: bool = False


class QueueItem(ApiModel):
    id: str
    track: Track
    added_by: str
    added_at_ms: int
    origin: QueueOrigin = QueueOrigin()


class QueueState(ApiModel):
    """Сериализуемый снимок очереди: уходит клиентам и в БД."""

    version: int = 0
    current: QueueItem | None = None
    upcoming: list[QueueItem] = []
    history: list[QueueItem] = []
    """Сначала — самые недавние."""
    repeat: RepeatMode = RepeatMode.OFF


def new_item_id() -> str:
    return secrets.token_urlsafe(8)


def make_item(track: Track, added_by: str, now_ms: int) -> QueueItem:
    return QueueItem(id=new_item_id(), track=track, added_by=added_by, added_at_ms=now_ms)


class Queue:
    def __init__(self, state: QueueState | None = None) -> None:
        state = state or QueueState()
        self.version = state.version
        self.current = state.current
        self.upcoming: list[QueueItem] = list(state.upcoming)
        self.history: deque[QueueItem] = deque(state.history, maxlen=HISTORY_LIMIT)
        self.repeat = state.repeat

    def snapshot(self) -> QueueState:
        return QueueState(
            version=self.version,
            current=self.current,
            upcoming=list(self.upcoming),
            history=list(self.history),
            repeat=self.repeat,
        )

    def _touch(self) -> None:
        self.version += 1

    def _index(self, item_id: str) -> int:
        for i, item in enumerate(self.upcoming):
            if item.id == item_id:
                return i
        raise NotFoundError("Этого трека уже нет в очереди.")

    def _archive_current(self) -> None:
        if self.current is not None:
            self.history.appendleft(self.current)
            self.current = None

    # ── Добавление ──────────────────────────────────────────────────────────────

    def add(self, items: list[QueueItem], *, index: int | None = None) -> None:
        """Вставить в позицию `index` предстоящих (по умолчанию — в конец)."""
        if not items:
            return
        if len(self.upcoming) + len(items) > QUEUE_LIMIT:
            raise ValidationError(f"В очереди не может быть больше {QUEUE_LIMIT} треков.")
        pos = len(self.upcoming) if index is None else max(0, min(index, len(self.upcoming)))
        self.upcoming[pos:pos] = items
        self._touch()

    def add_next(self, items: list[QueueItem]) -> None:
        self.add(items, index=0)

    def play_now(self, items: list[QueueItem]) -> QueueItem:
        """Первый элемент становится текущим, остальные — сразу за ним."""
        if not items:
            raise ValidationError("Нечего играть.")
        if len(items) > 1:
            self.add(items[1:], index=0)
        self._archive_current()
        self.current = items[0]
        self._touch()
        return items[0]

    # ── Правка ──────────────────────────────────────────────────────────────────

    def remove(self, item_id: str) -> tuple[QueueItem, int]:
        index = self._index(item_id)
        item = self.upcoming.pop(index)
        self._touch()
        return item, index

    def move(self, item_id: str, to_index: int) -> None:
        index = self._index(item_id)
        item = self.upcoming.pop(index)
        to_index = max(0, min(to_index, len(self.upcoming)))
        self.upcoming.insert(to_index, item)
        self._touch()

    def shuffle(self, rng: random.Random | None = None) -> None:
        (rng or random.SystemRandom()).shuffle(self.upcoming)
        self._touch()

    def clear(self) -> int:
        count = len(self.upcoming)
        self.upcoming.clear()
        self._touch()
        return count

    def set_repeat(self, mode: RepeatMode) -> None:
        self.repeat = mode
        self._touch()

    def find_history(self, item_id: str) -> QueueItem:
        for item in self.history:
            if item.id == item_id:
                return item
        raise NotFoundError("Трек не найден в истории.")

    # ── Переходы ────────────────────────────────────────────────────────────────

    def advance(self, *, natural_end: bool) -> QueueItem | None:
        """Перейти к следующему элементу.

        `natural_end` — трек доиграл сам: только тогда действует повтор трека. «Следующий» от
        пользователя всегда переключает трек; при повторе очереди сыгранный уходит в конец.
        """
        if natural_end and self.repeat is RepeatMode.TRACK and self.current is not None:
            self._touch()
            return self.current
        finished = self.current
        self._archive_current()
        if self.repeat is not RepeatMode.OFF and finished is not None:
            self.upcoming.append(finished.model_copy(update={"id": new_item_id()}))
        self.current = self.upcoming.pop(0) if self.upcoming else None
        self._touch()
        return self.current

    def previous(self) -> QueueItem | None:
        """Вернуть последний сыгранный; текущий встаёт первым в предстоящие."""
        if not self.history:
            return None
        if self.current is not None:
            self.upcoming.insert(0, self.current)
        self.current = self.history.popleft()
        self._touch()
        return self.current

    def play_item(self, item_id: str) -> QueueItem:
        """Сыграть элемент из предстоящих сейчас; остальные остаются на месте."""
        index = self._index(item_id)
        item = self.upcoming.pop(index)
        self._archive_current()
        self.current = item
        self._touch()
        return item
