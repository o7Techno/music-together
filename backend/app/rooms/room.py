"""Актор комнаты (SPEC §5): авторитетное состояние, последовательная обработка команд.

Все изменения идут под одним asyncio.Lock на комнату, каждое изменение воспроизведения
инкрементирует `PlaybackState.version`. Время и таймеры внедряются — логика детерминированно
тестируется на FakeClock/FakeTimers.

Ключевые схемы:
- смена трека → `loading` → барьер готовности (ready от разблокированных онлайн-клиентов,
  не дольше BARRIER_TIMEOUT_MS) → старт в будущем `anchor = now + START_LEAD_MS`;
- play после паузы → старт в будущем `now + RESUME_LEAD_MS` без барьера (трек уже загружен);
- seek во время воспроизведения → короткий барьер (клиенты перематывают и подтверждают готовность),
  затем старт через SEEK_LEAD_MS;
- окончание трека отслеживает сервер по таймеру длительности, а не по `ended` от клиентов.
"""

from __future__ import annotations

import asyncio
import secrets
import statistics
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from app.core.clock import Clock
from app.core.errors import ConflictError, ForbiddenError, RateLimitedError, ValidationError
from app.core.logging import get_logger
from app.core.ratelimit import RateLimiter
from app.providers.base import Track
from app.rooms.playback import (
    PlaybackState,
    PlaybackStatus,
    expected_position_ms,
    remaining_ms,
)
from app.rooms.queue import Queue, QueueItem, QueueState, RepeatMode, make_item
from app.rooms.timers import TimerHandle, Timers
from app.ws.protocol import (
    Ack,
    AddPosition,
    ChatMessage,
    ChatMessageEnvelope,
    ChatSend,
    ClientStatus,
    Closed,
    CloseReason,
    CmdNext,
    CmdPause,
    CmdPlay,
    CmdPlayItem,
    CmdPrev,
    CmdSeek,
    CmdSetRepeat,
    DriftReport,
    EventKind,
    EventMessage,
    MembersMessage,
    MemberView,
    PlaybackMessage,
    QueueClear,
    QueueMessage,
    QueueMove,
    QueueRemove,
    QueueShuffle,
    QueueSource,
    ReactionSend,
    Ready,
    RoomCommand,
    RoomEvent,
    RoomInfo,
    RoomInfoMessage,
    Snapshot,
    SyncState,
    SyncStats,
)

log = get_logger(__name__)

BARRIER_TIMEOUT_MS = 2500
START_LEAD_MS = 300
RESUME_LEAD_MS = 200
SEEK_BARRIER_TIMEOUT_MS = 1000
SEEK_LEAD_MS = 150
PREV_RESTART_THRESHOLD_MS = 3000
EVENTS_LIMIT = 100
CHAT_LIMIT = 200
CHAT_TTL_MS = 24 * 3600 * 1000
DRIFT_WINDOW_S = 30.0
STATS_BROADCAST_MS = 3000
LEAVE_GRACE_MS = 15_000
COMMAND_RATE_PER_S = 5.0
COMMAND_BURST = 8.0

ServerPayload = (
    Snapshot
    | PlaybackMessage
    | QueueMessage
    | MembersMessage
    | RoomInfoMessage
    | EventMessage
    | ChatMessageEnvelope
    | Ack
    | Closed
)


class Outbox(Protocol):
    """Доставка сообщений соединению. Не блокирует: у каждого соединения своя очередь."""

    def send(self, conn_id: str, message: ServerPayload) -> None: ...

    def close(self, conn_id: str, reason: CloseReason) -> None: ...


@dataclass(frozen=True)
class RoomUser:
    id: str
    name: str
    avatar_url: str | None = None


@dataclass
class ClientConn:
    conn_id: str
    user: RoomUser
    audio_unlocked: bool = False
    track_unavailable: bool = False
    sync: SyncState = SyncState.IDLE
    drift: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=120))
    """(monotonic s, |drift| ms)"""


@dataclass
class _Barrier:
    version: int
    awaiting: set[str]
    lead_ms: int
    timeout: TimerHandle


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


class Room:
    def __init__(
        self,
        *,
        room_id: str,
        slug: str,
        name: str,
        owner_id: str,
        clock: Clock,
        timers: Timers,
        outbox: Outbox,
        playback: PlaybackState | None = None,
        queue: QueueState | None = None,
        on_change: Callable[[Room], None] | None = None,
    ) -> None:
        self.id = room_id
        self.slug = slug
        self.name = name
        self.owner_id = owner_id
        self._clock = clock
        self._timers = timers
        self._out = outbox
        self._on_change = on_change or (lambda _room: None)
        self.lock = asyncio.Lock()

        self.playback = playback or PlaybackState()
        self.queue = Queue(queue)
        self.clients: dict[str, ClientConn] = {}
        self.events: deque[RoomEvent] = deque(maxlen=EVENTS_LIMIT)
        self.chat: deque[ChatMessage] = deque(maxlen=CHAT_LIMIT)
        self._barrier: _Barrier | None = None
        self._end_timer: TimerHandle | None = None
        self._stats_timer: TimerHandle | None = None
        self._stats_dirty = False
        self._leave_timers: dict[str, TimerHandle] = {}
        self._recently_online: set[str] = set()
        self._limiter = RateLimiter(COMMAND_RATE_PER_S, COMMAND_BURST, clock.monotonic)
        self.closed = False

    # ── Снимки и рассылка ───────────────────────────────────────────────────────

    @property
    def info(self) -> RoomInfo:
        return RoomInfo(id=self.id, slug=self.slug, name=self.name, owner_id=self.owner_id)

    def snapshot_for(self, conn_id: str) -> Snapshot:
        client = self.clients[conn_id]
        members, stats = self._members_view()
        return Snapshot(
            server_time=self._clock.now_ms(),
            self_user_id=client.user.id,
            room=self.info,
            playback=self.playback,
            queue=self.queue.snapshot(),
            members=members,
            stats=stats,
            events=list(self.events),
            chat=self._fresh_chat(),
        )

    def _broadcast(self, message: ServerPayload) -> None:
        for conn_id in self.clients:
            self._out.send(conn_id, message)

    def _publish_playback(self) -> None:
        self._broadcast(PlaybackMessage(state=self.playback))

    def _publish_queue(self) -> None:
        self._broadcast(QueueMessage(queue=self.queue.snapshot()))

    def _publish_members(self) -> None:
        members, stats = self._members_view()
        self._broadcast(MembersMessage(members=members, stats=stats))
        self._stats_dirty = False

    def _event(self, kind: EventKind, user: RoomUser | None, **fields: object) -> None:
        event = RoomEvent.model_validate(
            {
                "id": secrets.token_urlsafe(6),
                "at_ms": self._clock.now_ms(),
                "kind": kind,
                "user_id": user.id if user else None,
                "user_name": user.name if user else None,
                **fields,
            }
        )
        self.events.append(event)
        self._broadcast(EventMessage(event=event))

    def _changed(self) -> None:
        self._on_change(self)

    # ── Участники ───────────────────────────────────────────────────────────────

    def _members_view(self) -> tuple[list[MemberView], SyncStats]:
        now = self._clock.monotonic()
        by_user: dict[str, list[ClientConn]] = {}
        for client in self.clients.values():
            by_user.setdefault(client.user.id, []).append(client)

        members: list[MemberView] = []
        all_samples: list[float] = []
        for conns in by_user.values():
            # Статус участника — по «лучшему» его соединению (разблокированному, свежему).
            primary = max(conns, key=lambda c: (c.audio_unlocked, not c.track_unavailable))
            samples = [d for c in conns for (t, d) in c.drift if now - t <= DRIFT_WINDOW_S]
            all_samples.extend(samples)
            members.append(
                MemberView(
                    user_id=primary.user.id,
                    name=primary.user.name,
                    avatar_url=primary.user.avatar_url,
                    online=True,
                    connections=len(conns),
                    audio_unlocked=primary.audio_unlocked,
                    track_unavailable=primary.track_unavailable,
                    sync=primary.sync,
                    drift_median_ms=round(statistics.median(samples), 1) if samples else None,
                    drift_p95_ms=round(_percentile(samples, 0.95), 1) if samples else None,
                    is_owner=primary.user.id == self.owner_id,
                )
            )
        members.sort(key=lambda m: (not m.is_owner, m.name.lower()))
        stats = SyncStats(
            median_ms=round(statistics.median(all_samples), 1) if all_samples else None,
            p95_ms=round(_percentile(all_samples, 0.95), 1) if all_samples else None,
            samples=len(all_samples),
        )
        return members, stats

    def _user_online(self, user_id: str) -> bool:
        return any(c.user.id == user_id for c in self.clients.values())

    async def join(self, conn_id: str, user: RoomUser) -> Snapshot:
        async with self.lock:
            first_conn = not self._user_online(user.id)
            self.clients[conn_id] = ClientConn(conn_id=conn_id, user=user)
            pending_leave = self._leave_timers.pop(user.id, None)
            if pending_leave is not None:
                pending_leave.cancel()
            if first_conn and user.id not in self._recently_online:
                self._event(EventKind.JOINED, user)
            self._recently_online.add(user.id)
            self._publish_members()
            return self.snapshot_for(conn_id)

    async def leave(self, conn_id: str) -> None:
        async with self.lock:
            client = self.clients.pop(conn_id, None)
            if client is None:
                return
            if self._barrier is not None:
                self._barrier.awaiting.discard(conn_id)
                if not self._barrier.awaiting:
                    self._finish_barrier()
            user = client.user
            if not self._user_online(user.id):
                self._leave_timers[user.id] = self._timers.call_later(
                    LEAVE_GRACE_MS, lambda: self._leave_grace_expired(user)
                )
            if not self.clients:
                # Комната без слушателей замирает на паузе, состояние сохраняется (SPEC §4.2).
                self._pause(by=None)
            self._publish_members()

    async def _leave_grace_expired(self, user: RoomUser) -> None:
        async with self.lock:
            self._leave_timers.pop(user.id, None)
            if self._user_online(user.id):
                return
            self._recently_online.discard(user.id)
            self._event(EventKind.LEFT, user)

    async def update_client_status(self, conn_id: str, status: ClientStatus) -> None:
        async with self.lock:
            client = self.clients.get(conn_id)
            if client is None:
                return
            changed = (
                client.audio_unlocked != status.audio_unlocked
                or client.track_unavailable != status.track_unavailable
                or client.sync != status.sync
            )
            client.audio_unlocked = status.audio_unlocked
            client.track_unavailable = status.track_unavailable
            client.sync = status.sync
            if self._barrier is not None and (
                not client.audio_unlocked or client.track_unavailable
            ):
                # Клиент больше не может участвовать в барьере — не ждём его.
                self._barrier.awaiting.discard(conn_id)
                if not self._barrier.awaiting:
                    self._finish_barrier()
            if changed:
                self._publish_members()

    async def report_drift(self, conn_id: str, report: DriftReport) -> None:
        async with self.lock:
            client = self.clients.get(conn_id)
            if client is None or self.playback.status is not PlaybackStatus.PLAYING:
                return
            client.drift.append((self._clock.monotonic(), abs(report.drift_ms)))
            self._stats_dirty = True
            if self._stats_timer is None:
                self._stats_timer = self._timers.call_later(STATS_BROADCAST_MS, self._stats_tick)

    async def _stats_tick(self) -> None:
        async with self.lock:
            self._stats_timer = None
            if self._stats_dirty and self.clients:
                self._publish_members()

    def kick(self, user_id: str) -> RoomUser | None:
        """Закрыть все соединения пользователя. Вызывается под `lock` менеджером."""
        kicked = [c for c in self.clients.values() if c.user.id == user_id]
        for client in kicked:
            self._out.close(client.conn_id, CloseReason.KICKED)
        return kicked[0].user if kicked else None

    def close_all(self, reason: CloseReason) -> None:
        self.closed = True
        for timer in (self._end_timer, self._stats_timer, *self._leave_timers.values()):
            if timer is not None:
                timer.cancel()
        if self._barrier is not None:
            self._barrier.timeout.cancel()
        for conn_id in list(self.clients):
            self._out.close(conn_id, reason)

    def rename(self, name: str, by: RoomUser) -> None:
        self.name = name
        self._broadcast(RoomInfoMessage(room=self.info))
        self._event(EventKind.RENAMED, by, title=name)
        self._changed()

    # ── Воспроизведение: внутренние переходы ────────────────────────────────────

    def _set_playback(self, by: RoomUser | None, **changes: object) -> None:
        self.playback = self.playback.model_copy(
            update={
                **changes,
                "version": self.playback.version + 1,
                "updated_by": by.id if by else None,
            }
        )

    def _cancel_end_timer(self) -> None:
        if self._end_timer is not None:
            self._end_timer.cancel()
            self._end_timer = None

    def _cancel_barrier(self) -> None:
        if self._barrier is not None:
            self._barrier.timeout.cancel()
            self._barrier = None

    def _schedule_end_timer(self) -> None:
        self._cancel_end_timer()
        if self.playback.status is not PlaybackStatus.PLAYING or self.playback.duration_ms <= 0:
            return
        version = self.playback.version
        delay = remaining_ms(self.playback, self._clock.now_ms())

        async def on_end() -> None:
            async with self.lock:
                if self.playback.version != version or self.closed:
                    return
                self._end_timer = None
                self._advance(by=None, natural_end=True)

        self._end_timer = self._timers.call_later(delay, on_end)

    def _load(self, item: QueueItem | None, by: RoomUser | None, position_ms: int = 0) -> None:
        """Перейти на элемент очереди: `loading` + барьер, либо остановка, если элемента нет."""
        self._cancel_end_timer()
        self._cancel_barrier()
        if item is None:
            self._set_playback(
                by,
                queue_item_id=None,
                track_id=None,
                status=PlaybackStatus.PAUSED,
                position_ms=0,
                anchor_server_ms=self._clock.now_ms(),
                duration_ms=0,
            )
            self._publish_playback()
            self._changed()
            return
        self._set_playback(
            by,
            queue_item_id=item.id,
            track_id=item.track.id,
            status=PlaybackStatus.LOADING,
            position_ms=position_ms,
            anchor_server_ms=self._clock.now_ms(),
            duration_ms=item.track.duration_ms,
        )
        self._publish_playback()
        self._start_barrier(BARRIER_TIMEOUT_MS, START_LEAD_MS)
        self._changed()

    def _start_barrier(self, timeout_ms: int, lead_ms: int) -> None:
        self._cancel_barrier()
        awaiting = {
            c.conn_id for c in self.clients.values() if c.audio_unlocked and not c.track_unavailable
        }
        version = self.playback.version

        async def on_timeout() -> None:
            async with self.lock:
                if self._barrier is not None and self._barrier.version == version:
                    log.info("barrier_timeout", room=self.slug, missing=len(self._barrier.awaiting))
                    self._finish_barrier()

        self._barrier = _Barrier(
            version=version,
            awaiting=awaiting,
            lead_ms=lead_ms,
            timeout=self._timers.call_later(timeout_ms, on_timeout),
        )
        if not awaiting:
            self._finish_barrier()

    def _finish_barrier(self) -> None:
        barrier = self._barrier
        if barrier is None:
            return
        barrier.timeout.cancel()
        self._barrier = None
        if self.playback.status is not PlaybackStatus.LOADING:
            return
        self._set_playback(
            None,
            status=PlaybackStatus.PLAYING,
            anchor_server_ms=self._clock.now_ms() + barrier.lead_ms,
        )
        self._publish_playback()
        self._schedule_end_timer()

    def _pause(self, by: RoomUser | None) -> bool:
        status = self.playback.status
        if status is PlaybackStatus.PAUSED:
            return False
        self._cancel_end_timer()
        self._cancel_barrier()
        position = expected_position_ms(self.playback, self._clock.now_ms())
        self._set_playback(
            by,
            status=PlaybackStatus.PAUSED,
            position_ms=position,
            anchor_server_ms=self._clock.now_ms(),
        )
        self._publish_playback()
        self._changed()
        return True

    def _advance(self, by: RoomUser | None, *, natural_end: bool) -> None:
        item = self.queue.advance(natural_end=natural_end)
        self._publish_queue()
        self._load(item, by)

    def _check_expected(self, expected: str | None) -> None:
        if expected != self.playback.queue_item_id:
            raise ConflictError

    # ── Сообщения клиентов ──────────────────────────────────────────────────────

    async def ready(self, conn_id: str, message: Ready) -> None:
        async with self.lock:
            barrier = self._barrier
            if barrier is None or barrier.version != message.version:
                return
            barrier.awaiting.discard(conn_id)
            if not barrier.awaiting:
                self._finish_barrier()

    def _rate_check(self, user: RoomUser) -> None:
        if not self._limiter.allow(user.id):
            raise RateLimitedError

    async def handle(self, conn_id: str, cmd: RoomCommand) -> None:
        """Применить команду. Бросает AppError — вызывающий шлёт клиенту `error`."""
        async with self.lock:
            client = self.clients.get(conn_id)
            if client is None:
                raise ForbiddenError("Вы не в комнате.")
            user = client.user
            if not isinstance(cmd, ChatSend | ReactionSend):
                self._rate_check(user)
            self._apply(user, cmd)
            self._out.send(conn_id, Ack(client_msg_id=cmd.client_msg_id))

    def _apply(self, user: RoomUser, cmd: RoomCommand) -> None:  # noqa: PLR0912, PLR0915 — диспетчер
        match cmd:
            case CmdPlay():
                self._cmd_play(user)
            case CmdPause():
                if self._pause(user):
                    self._event(EventKind.PAUSE, user, position_ms=self.playback.position_ms)
            case CmdSeek(position_ms=position, expected_queue_item_id=expected):
                self._check_expected(expected)
                self._seek(user, position)
                self._event(EventKind.SEEK, user, position_ms=self.playback.position_ms)
            case CmdNext(expected_queue_item_id=expected):
                self._check_expected(expected)
                title = self.queue.current.track.title if self.queue.current else None
                self._advance(user, natural_end=False)
                self._event(EventKind.NEXT, user, title=title)
            case CmdPrev(expected_queue_item_id=expected):
                self._check_expected(expected)
                self._cmd_prev(user)
            case CmdPlayItem(queue_item_id=item_id):
                item = self.queue.play_item(item_id)
                self._publish_queue()
                self._load(item, user)
                self._event(EventKind.PLAY_ITEM, user, title=item.track.title)
            case CmdSetRepeat(mode=mode):
                self.queue.set_repeat(mode)
                self._publish_queue()
                self._event(EventKind.REPEAT, user, repeat=mode)
                self._changed()
            case QueueRemove(item_id=item_id):
                removed, _ = self.queue.remove(item_id)
                self._publish_queue()
                self._event(EventKind.QUEUE_REMOVE, user, title=removed.track.title)
                self._changed()
            case QueueMove(item_id=item_id, to_index=to_index):
                self.queue.move(item_id, to_index)
                self._publish_queue()
                self._changed()
            case QueueShuffle():
                self.queue.shuffle()
                self._publish_queue()
                self._event(EventKind.QUEUE_SHUFFLE, user)
                self._changed()
            case QueueClear():
                count = self.queue.clear()
                self._publish_queue()
                self._event(EventKind.QUEUE_CLEAR, user, count=count)
                self._changed()
            case ChatSend(text=text):
                self._chat(user, text=text.strip())
            case ReactionSend(emoji=emoji):
                self._chat(user, emoji=emoji, track_id=self.playback.track_id)

    def _cmd_play(self, user: RoomUser) -> None:
        state = self.playback
        if state.status is not PlaybackStatus.PAUSED:
            return
        if state.queue_item_id is None:
            # Ничего не играет — берём следующий из очереди.
            if not self.queue.upcoming:
                raise ValidationError("Очередь пуста — добавьте трек.")
            self._advance(user, natural_end=False)
            self._event(EventKind.PLAY, user)
            return
        position = state.position_ms
        if state.duration_ms and position >= state.duration_ms - 200:
            position = 0
        self._set_playback(
            user,
            status=PlaybackStatus.PLAYING,
            position_ms=position,
            anchor_server_ms=self._clock.now_ms() + RESUME_LEAD_MS,
        )
        self._publish_playback()
        self._schedule_end_timer()
        self._event(EventKind.PLAY, user, position_ms=position)
        self._changed()

    def _seek(self, user: RoomUser, position_ms: int) -> None:
        state = self.playback
        if state.queue_item_id is None:
            raise ValidationError("Сейчас ничего не играет.")
        limit = max(0, state.duration_ms - 500)
        position = max(0, min(position_ms, limit))
        if state.status is PlaybackStatus.PAUSED:
            self._set_playback(user, position_ms=position, anchor_server_ms=self._clock.now_ms())
            self._publish_playback()
            self._changed()
            return
        # Играет или грузится: короткий барьер, чтобы все успели перемотать, затем общий старт.
        self._cancel_end_timer()
        self._set_playback(
            user,
            status=PlaybackStatus.LOADING,
            position_ms=position,
            anchor_server_ms=self._clock.now_ms(),
        )
        self._publish_playback()
        self._start_barrier(SEEK_BARRIER_TIMEOUT_MS, SEEK_LEAD_MS)
        self._changed()

    def _cmd_prev(self, user: RoomUser) -> None:
        position = expected_position_ms(self.playback, self._clock.now_ms())
        if position > PREV_RESTART_THRESHOLD_MS or not self.queue.history:
            if self.playback.queue_item_id is None:
                return
            self._seek(user, 0)
            self._event(EventKind.SEEK, user, position_ms=0)
            return
        item = self.queue.previous()
        self._publish_queue()
        self._load(item, user)
        self._event(EventKind.PREV, user, title=item.track.title if item else None)

    # ── Очередь: добавление (треки уже получены провайдером добавляющего) ───────

    async def add_tracks(
        self,
        conn_id: str,
        client_msg_id: str,
        tracks: list[Track],
        *,
        position: AddPosition,
        index: int | None,
        source: QueueSource | None,
    ) -> None:
        async with self.lock:
            client = self.clients.get(conn_id)
            if client is None:
                raise ForbiddenError("Вы не в комнате.")
            user = client.user
            self._rate_check(user)
            now = self._clock.now_ms()
            items = [make_item(t, user.id, now) for t in tracks]
            was_idle = self.queue.current is None
            if index is not None:
                self.queue.add(items, index=index)
            elif position is AddPosition.NOW:
                first = self.queue.play_now(items)
                self._publish_queue()
                self._load(first, user)
            elif position is AddPosition.NEXT:
                self.queue.add_next(items)
            else:
                self.queue.add(items)
            if was_idle and position is not AddPosition.NOW and self.queue.current is None:
                # Пустая комната: первый добавленный трек сразу начинает играть.
                self._advance(user, natural_end=False)
            else:
                self._publish_queue()
            self._event(
                EventKind.QUEUE_ADD,
                user,
                count=len(items),
                title=items[0].track.title if len(items) == 1 else None,
                source=source,
            )
            self._changed()
            self._out.send(conn_id, Ack(client_msg_id=client_msg_id))

    def find_history_item(self, item_id: str) -> QueueItem:
        return self.queue.find_history(item_id)

    # ── Чат ─────────────────────────────────────────────────────────────────────

    def _fresh_chat(self) -> list[ChatMessage]:
        cutoff = self._clock.now_ms() - CHAT_TTL_MS
        while self.chat and self.chat[0].at_ms < cutoff:
            self.chat.popleft()
        return list(self.chat)

    def _chat(
        self,
        user: RoomUser,
        *,
        text: str | None = None,
        emoji: str | None = None,
        track_id: str | None = None,
    ) -> None:
        if text is not None and not text:
            raise ValidationError("Пустое сообщение.")
        message = ChatMessage(
            id=secrets.token_urlsafe(6),
            at_ms=self._clock.now_ms(),
            user_id=user.id,
            user_name=user.name,
            text=text,
            emoji=emoji,
            track_id=track_id,
        )
        self._fresh_chat()
        self.chat.append(message)
        self._broadcast(ChatMessageEnvelope(message=message))

    # ── Сохранение ──────────────────────────────────────────────────────────────

    def persisted_playback(self) -> PlaybackState:
        """Состояние для БД: если играет — фиксируем текущую позицию и ставим на паузу.

        После рестарта сервера комната продолжается с паузы на сохранённой позиции (SPEC §7.1).
        """
        state = self.playback
        if state.status is PlaybackStatus.PAUSED:
            return state
        return state.model_copy(
            update={
                "status": PlaybackStatus.PAUSED,
                "position_ms": expected_position_ms(state, self._clock.now_ms())
                if state.status is PlaybackStatus.PLAYING
                else state.position_ms,
                "anchor_server_ms": self._clock.now_ms(),
            }
        )

    @property
    def repeat(self) -> RepeatMode:
        return self.queue.repeat
