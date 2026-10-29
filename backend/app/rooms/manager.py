"""Живые комнаты в памяти процесса + сохранение в PostgreSQL с дебаунсом (SPEC §7.1).

Комната поднимается из БД при первом подключении, сохраняется после значимых изменений
(не чаще раза в SAVE_DEBOUNCE_S) и при остановке сервера. Пустые комнаты выгружаются из памяти.
"""

from __future__ import annotations

import asyncio
import contextlib

from pydantic import ValidationError as PydanticValidationError

from app.core.clock import Clock
from app.core.logging import get_logger
from app.db import models
from app.db.session import Database
from app.rooms.playback import PlaybackState
from app.rooms.queue import QueueState
from app.rooms.room import Outbox, Room
from app.rooms.timers import Timers
from app.ws.protocol import CloseReason

log = get_logger(__name__)

SAVE_DEBOUNCE_S = 1.0
IDLE_EVICT_S = 30 * 60


class RoomManager:
    def __init__(self, db: Database, clock: Clock, timers: Timers, outbox: Outbox) -> None:
        self._db = db
        self._clock = clock
        self._timers = timers
        self._outbox = outbox
        self._rooms: dict[str, Room] = {}
        self._load_lock = asyncio.Lock()
        self._save_tasks: dict[str, asyncio.Task[None]] = {}
        self._idle_since: dict[str, float] = {}

    def __len__(self) -> int:
        return len(self._rooms)

    def loaded(self, room_id: str) -> Room | None:
        return self._rooms.get(room_id)

    async def get(self, record: models.Room) -> Room:
        room = self._rooms.get(record.id)
        if room is not None:
            return room
        async with self._load_lock:
            room = self._rooms.get(record.id)
            if room is None:
                room = self._build(record)
                self._rooms[record.id] = room
            return room

    def _build(self, record: models.Room) -> Room:
        playback: PlaybackState | None = None
        queue: QueueState | None = None
        try:
            if "playback" in record.state:
                playback = PlaybackState.model_validate(record.state["playback"])
            if "queue" in record.state:
                queue = QueueState.model_validate(record.state["queue"])
        except PydanticValidationError:
            log.exception("room_state_corrupted", room=record.slug)
        return Room(
            room_id=record.id,
            slug=record.slug,
            name=record.name,
            owner_id=record.owner_id,
            clock=self._clock,
            timers=self._timers,
            outbox=self._outbox,
            playback=playback,
            queue=queue,
            on_change=self._schedule_save,
        )

    # ── Сохранение ──────────────────────────────────────────────────────────────

    def _schedule_save(self, room: Room) -> None:
        task = self._save_tasks.get(room.id)
        if task is not None and not task.done():
            return
        self._save_tasks[room.id] = asyncio.get_running_loop().create_task(self._save_later(room))

    async def _save_later(self, room: Room) -> None:
        await asyncio.sleep(SAVE_DEBOUNCE_S)
        await self.save(room)

    async def save(self, room: Room) -> None:
        async with room.lock:
            state = {
                "playback": room.persisted_playback().model_dump(mode="json", by_alias=False),
                "queue": room.queue.snapshot().model_dump(mode="json", by_alias=False),
            }
            name = room.name
        try:
            async with self._db.sessionmaker() as db:
                record = await db.get(models.Room, room.id)
                if record is None:  # комнату удалили
                    return
                record.state = state
                record.name = name
                await db.commit()
        except Exception:
            log.exception("room_save_failed", room=room.slug)

    async def save_all(self) -> None:
        for task in self._save_tasks.values():
            task.cancel()
        await asyncio.gather(*(self.save(room) for room in list(self._rooms.values())))

    # ── Жизненный цикл ──────────────────────────────────────────────────────────

    async def drop(self, room_id: str, reason: CloseReason) -> None:
        """Комнату удалили: закрыть соединения и забыть."""
        room = self._rooms.pop(room_id, None)
        task = self._save_tasks.pop(room_id, None)
        if task is not None:
            task.cancel()
        if room is not None:
            async with room.lock:
                room.close_all(reason)

    async def shutdown(self) -> None:
        """Graceful shutdown: сохранить всё и попросить клиентов переподключиться."""
        await self.save_all()
        for room in self._rooms.values():
            async with room.lock:
                room.close_all(CloseReason.RESTART)

    async def evict_idle(self) -> int:
        """Выгрузить из памяти комнаты без подключений дольше IDLE_EVICT_S."""
        now = self._clock.monotonic()
        evicted = 0
        for room_id, room in list(self._rooms.items()):
            if room.clients:
                self._idle_since.pop(room_id, None)
                continue
            since = self._idle_since.setdefault(room_id, now)
            if now - since >= IDLE_EVICT_S:
                await self.save(room)
                async with room.lock:
                    if room.clients:
                        continue
                    room.close_all(CloseReason.RESTART)
                    self._rooms.pop(room_id, None)
                    self._idle_since.pop(room_id, None)
                    evicted += 1
        return evicted

    async def run_janitor(self, interval_s: float = 60) -> None:
        while True:
            await asyncio.sleep(interval_s)
            with contextlib.suppress(Exception):
                await self.evict_idle()
