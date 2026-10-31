"""Фоновые запросы волны (SPEC-wave §4.1): вне `room.lock` и вне цикла чтения WebSocket.

Актор комнаты решает, что нужно, драйвер ходит в Яндекс и возвращает результат актору; поздние
ответы тот отбрасывает по `generation`. Пользователь читается из БД на каждый запрос: объект из
WebSocket-соединения живёт часами и мог устареть (токен обновили, из аккаунта вышли).
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.db.models import User
from app.db.session import Database
from app.providers.base import (
    MusicProvider,
    ProviderAuthError,
    ProviderError,
    SubscriptionRequiredError,
    Track,
    TrackUnavailableError,
    WaveBatch,
    WaveFeedback,
    WaveFeedbackKind,
    WaveSessionLostError,
)

if TYPE_CHECKING:
    from app.providers.factory import ProviderFactory
    from app.rooms.room import Room

log = get_logger(__name__)

FEEDBACK_QUEUE_LIMIT = 200
FEEDBACK_BATCH = 20
FEEDBACK_RETRY_DELAYS_S = (1.0, 5.0)
FLUSH_TIMEOUT_S = 2.0
# Лайк в коллекции и явный дизлайк — личные действия: настройка «не учить» их не отменяет.
ALWAYS_SENT = {WaveFeedbackKind.LIKE, WaveFeedbackKind.UNLIKE, WaveFeedbackKind.DISLIKE}


@dataclass
class WaveRequest:
    generation: int
    owner_id: str
    owner_name: str | None
    session_id: str | None
    seeds: list[str]
    recent_ids: list[str]


@dataclass
class _FeedbackQueue:
    items: deque[tuple[str, WaveFeedback]] = field(
        default_factory=lambda: deque(maxlen=FEEDBACK_QUEUE_LIMIT)
    )
    task: asyncio.Task[None] | None = None


class ProviderWaveDriver:
    def __init__(self, db: Database, providers: ProviderFactory) -> None:
        self._db = db
        self._providers = providers
        self._tasks: set[asyncio.Task[None]] = set()
        self._feedback: dict[str, _FeedbackQueue] = {}

    def _spawn(self, coro: object) -> asyncio.Task[None]:
        task: asyncio.Task[None] = asyncio.get_running_loop().create_task(coro)  # type: ignore[arg-type]  # корутина
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _user(self, user_id: str) -> User | None:
        async with self._db.sessionmaker() as db:
            return await db.get(User, user_id)

    async def _provider(self, user_id: str) -> tuple[User, MusicProvider]:
        user = await self._user(user_id)
        if user is None:
            raise ProviderAuthError
        return user, self._providers.for_user(user)

    # ── Порции ──────────────────────────────────────────────────────────────────

    def request_batch(self, room: Room, request: WaveRequest) -> None:
        self._spawn(self._fetch(room, request))

    async def _fetch(self, room: Room, request: WaveRequest) -> None:
        try:
            batch = await self._load_batch(request)
        except (ProviderAuthError, SubscriptionRequiredError) as e:
            log.info("wave_owner_cannot_play", room=room.slug, error=e.code)
            await room.apply_wave_failure(request.generation, fatal=True, owner_id=request.owner_id)
        except ProviderError as e:
            log.info("wave_batch_failed", room=room.slug, error=e.code)
            await room.apply_wave_failure(
                request.generation, fatal=False, owner_id=request.owner_id
            )
        except Exception:
            log.exception("wave_batch_crashed", room=room.slug)
            await room.apply_wave_failure(
                request.generation, fatal=False, owner_id=request.owner_id
            )
        else:
            await room.apply_wave_batch(
                request.generation,
                batch,
                owner_id=request.owner_id,
                owner_name=request.owner_name,
            )

    async def _load_batch(self, request: WaveRequest) -> WaveBatch:
        user, provider = await self._provider(request.owner_id)
        batch: WaveBatch | None = None
        if request.session_id is not None:
            try:
                batch = await provider.next_wave_tracks(request.session_id, request.recent_ids)
            except WaveSessionLostError:
                log.info("wave_session_lost", user_id=request.owner_id)
        if batch is None:
            batch = await provider.start_wave(
                request.seeds, request.recent_ids, incognito=not user.wave_learning
            )
        playable = await self._playable_by_owner(provider, batch.tracks)
        return batch.model_copy(update={"tracks": playable})

    async def _playable_by_owner(self, provider: MusicProvider, tracks: list[Track]) -> list[Track]:
        """Трек, недоступный владельцу, пропускаем без проигрывания (SPEC-wave §7)."""
        playable: list[Track] = []
        for track in tracks:
            try:
                await provider.get_stream(track.id)
            except TrackUnavailableError:
                continue
            except SubscriptionRequiredError:
                raise
            except ProviderAuthError:
                raise
            except ProviderError:
                log.info("wave_stream_check_failed", track_id=track.id)
            playable.append(track)
        return playable

    # ── Фидбек ──────────────────────────────────────────────────────────────────

    def feedback(self, user_id: str, session_id: str, event: WaveFeedback) -> None:
        queue = self._feedback.setdefault(user_id, _FeedbackQueue())
        queue.items.append((session_id, event))
        if queue.task is None or queue.task.done():
            queue.task = self._spawn(self._drain(user_id, queue))

    async def _drain(self, user_id: str, queue: _FeedbackQueue) -> None:
        """Ошибки фидбека только логируются и никогда не затрагивают воспроизведение."""
        while queue.items:
            session_id = queue.items[0][0]
            events: list[WaveFeedback] = []
            while queue.items and queue.items[0][0] == session_id and len(events) < FEEDBACK_BATCH:
                events.append(queue.items.popleft()[1])
            try:
                await self._send(user_id, session_id, events)
            except Exception:
                log.warning("wave_feedback_dropped", user_id=user_id, count=len(events))

    async def _send(self, user_id: str, session_id: str, events: list[WaveFeedback]) -> None:
        user, provider = await self._provider(user_id)
        if not user.wave_learning:
            events = [e for e in events if e.kind in ALWAYS_SENT]
        if not events:
            return
        for delay in (*FEEDBACK_RETRY_DELAYS_S, None):
            try:
                await provider.send_wave_feedback(session_id, events)
            except ProviderAuthError:
                raise
            except ProviderError:
                if delay is None:
                    raise
                await asyncio.sleep(delay)
            else:
                log.debug("wave_feedback_sent", kinds=[e.kind.value for e in events])
                return

    def dislike(self, user_id: str, track_id: str) -> None:
        self._spawn(self._dislike(user_id, track_id))

    async def _dislike(self, user_id: str, track_id: str) -> None:
        try:
            _, provider = await self._provider(user_id)
            await provider.dislike_track(track_id)
        except Exception:
            log.warning("wave_dislike_failed", user_id=user_id, track_id=track_id)

    async def close(self) -> None:
        """При остановке — короткая попытка отправить остаток: фидбек не критичен."""
        pending = list(self._tasks)
        if pending:
            await asyncio.wait(pending, timeout=FLUSH_TIMEOUT_S)
        for task in pending:
            task.cancel()
