"""Протокол WebSocket (SPEC §7.4). Источник истины: TS-типы генерируются из этих моделей.

Все сообщения — JSON с полем `type`. Команды несут `clientMsgId`, сервер отвечает `ack` или `error`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from app.core.schema import ApiModel
from app.rooms.playback import PlaybackState
from app.rooms.queue import QueueState, RepeatMode
from app.rooms.wave import RoomSettings, WaveMode, WaveSeed, WaveView

MAX_BATCH_TRACKS = 500
MAX_MESSAGE_BYTES = 64 * 1024
WAVE_SETTINGS_LIMIT = 5

WaveSetting = Annotated[str, Field(pattern=r"^setting[A-Za-z]+:[a-z-]{1,32}$")]

# ── Клиент → сервер ─────────────────────────────────────────────────────────────


class Ping(ApiModel):
    type: Literal["ping"] = "ping"
    t0: float
    """Клиентское время отправки, epoch ms (performance.timeOrigin + performance.now())."""


class Ready(ApiModel):
    """Трек загружен и готов к старту для состояния с этой версией."""

    type: Literal["ready"] = "ready"
    version: int


class SyncState(StrEnum):
    IN_SYNC = "in_sync"
    CATCHING_UP = "catching_up"
    BUFFERING = "buffering"
    UNSTABLE = "unstable"
    IDLE = "idle"


class ClientStatus(ApiModel):
    type: Literal["client_status"] = "client_status"
    audio_unlocked: bool
    track_unavailable: bool = False
    sync: SyncState = SyncState.IDLE


class DriftReport(ApiModel):
    type: Literal["drift_report"] = "drift_report"
    drift_ms: float
    playback_rate: float = 1.0
    offset_ms: float = 0.0
    rtt_ms: float = 0.0
    output_latency_ms: float | None = None


class CmdPlay(ApiModel):
    type: Literal["cmd.play"] = "cmd.play"
    client_msg_id: str


class CmdPause(ApiModel):
    type: Literal["cmd.pause"] = "cmd.pause"
    client_msg_id: str


class CmdSeek(ApiModel):
    type: Literal["cmd.seek"] = "cmd.seek"
    client_msg_id: str
    position_ms: int = Field(ge=0)
    expected_queue_item_id: str | None


class CmdNext(ApiModel):
    type: Literal["cmd.next"] = "cmd.next"
    client_msg_id: str
    expected_queue_item_id: str | None


class CmdPrev(ApiModel):
    type: Literal["cmd.prev"] = "cmd.prev"
    client_msg_id: str
    expected_queue_item_id: str | None


class CmdPlayItem(ApiModel):
    type: Literal["cmd.play_item"] = "cmd.play_item"
    client_msg_id: str
    queue_item_id: str


class CmdSetRepeat(ApiModel):
    type: Literal["cmd.set_repeat"] = "cmd.set_repeat"
    client_msg_id: str
    mode: RepeatMode


class AddPosition(StrEnum):
    END = "end"
    NEXT = "next"
    NOW = "now"


class QueueSource(ApiModel):
    """Откуда добавлены треки — для события в ленте («37 треков из плейлиста X»)."""

    kind: Literal["album", "playlist", "artist", "liked", "search", "link", "history", "undo"]
    title: str | None = None


class QueueAdd(ApiModel):
    type: Literal["queue.add"] = "queue.add"
    client_msg_id: str
    track_ids: list[str] = Field(min_length=1, max_length=MAX_BATCH_TRACKS)
    position: AddPosition = AddPosition.END
    index: int | None = Field(default=None, ge=0)
    """Явная позиция в предстоящих (для «Отменить удаление»); перекрывает `position`."""
    source: QueueSource | None = None


class QueueRemove(ApiModel):
    type: Literal["queue.remove"] = "queue.remove"
    client_msg_id: str
    item_id: str


class QueueMove(ApiModel):
    type: Literal["queue.move"] = "queue.move"
    client_msg_id: str
    item_id: str
    to_index: int = Field(ge=0)


class QueueShuffle(ApiModel):
    type: Literal["queue.shuffle"] = "queue.shuffle"
    client_msg_id: str


class QueueClear(ApiModel):
    type: Literal["queue.clear"] = "queue.clear"
    client_msg_id: str


class ChatSend(ApiModel):
    type: Literal["chat.send"] = "chat.send"
    client_msg_id: str
    text: str = Field(min_length=1, max_length=500)


class ReactionSend(ApiModel):
    type: Literal["chat.react"] = "chat.react"
    client_msg_id: str
    emoji: str = Field(min_length=1, max_length=16)


class WaveStart(ApiModel):
    type: Literal["wave.start"] = "wave.start"
    client_msg_id: str
    mode: WaveMode
    seed: WaveSeed | None = None
    settings: list[WaveSetting] = Field(default=[], max_length=WAVE_SETTINGS_LIMIT)
    expected_wave_id: str | None = None
    """Какую волну заменяем: два одновременных запуска не заменят друг друга молча."""


class WaveStop(ApiModel):
    type: Literal["wave.stop"] = "wave.stop"
    client_msg_id: str


class WaveUpdateSettings(ApiModel):
    type: Literal["wave.update_settings"] = "wave.update_settings"
    client_msg_id: str
    settings: list[WaveSetting] = Field(max_length=WAVE_SETTINGS_LIMIT)


class WavePin(ApiModel):
    type: Literal["wave.pin"] = "wave.pin"
    client_msg_id: str
    item_id: str


class WaveRemove(ApiModel):
    type: Literal["wave.remove"] = "wave.remove"
    client_msg_id: str
    item_id: str


class TrackDislike(ApiModel):
    """«Не нравится»: пропуск трека волны, а у её владельца — ещё и дизлайк в его аккаунте."""

    type: Literal["track.dislike"] = "track.dislike"
    client_msg_id: str
    expected_queue_item_id: str | None


RoomCommand = (
    CmdPlay
    | CmdPause
    | CmdSeek
    | CmdNext
    | CmdPrev
    | CmdPlayItem
    | CmdSetRepeat
    | QueueRemove
    | QueueMove
    | QueueShuffle
    | QueueClear
    | ChatSend
    | ReactionSend
    | WaveStart
    | WaveStop
    | WaveUpdateSettings
    | WavePin
    | WaveRemove
    | TrackDislike
)
"""Команды, которые актор комнаты применяет синхронно (без I/O). `queue.add` резолвится отдельно."""

ClientMessage = Annotated[
    Ping
    | Ready
    | ClientStatus
    | DriftReport
    | CmdPlay
    | CmdPause
    | CmdSeek
    | CmdNext
    | CmdPrev
    | CmdPlayItem
    | CmdSetRepeat
    | QueueAdd
    | QueueRemove
    | QueueMove
    | QueueShuffle
    | QueueClear
    | ChatSend
    | ReactionSend
    | WaveStart
    | WaveStop
    | WaveUpdateSettings
    | WavePin
    | WaveRemove
    | TrackDislike,
    Field(discriminator="type"),
]
client_message_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)

# ── Сервер → клиент ─────────────────────────────────────────────────────────────


class RoomInfo(ApiModel):
    id: str
    slug: str
    name: str
    owner_id: str
    settings: RoomSettings = RoomSettings()


class MemberView(ApiModel):
    user_id: str
    name: str
    avatar_url: str | None = None
    online: bool
    connections: int
    audio_unlocked: bool
    track_unavailable: bool
    sync: SyncState
    drift_median_ms: float | None = None
    drift_p95_ms: float | None = None
    is_owner: bool = False


class SyncStats(ApiModel):
    """Статистика рассинхрона по комнате (|drift| за последние ~30 с по всем клиентам)."""

    median_ms: float | None = None
    p95_ms: float | None = None
    samples: int = 0


class EventKind(StrEnum):
    JOINED = "joined"
    LEFT = "left"
    PLAY = "play"
    PAUSE = "pause"
    SEEK = "seek"
    NEXT = "next"
    PREV = "prev"
    PLAY_ITEM = "play_item"
    QUEUE_ADD = "queue_add"
    QUEUE_REMOVE = "queue_remove"
    QUEUE_MOVE = "queue_move"
    QUEUE_SHUFFLE = "queue_shuffle"
    QUEUE_CLEAR = "queue_clear"
    REPEAT = "repeat"
    RENAMED = "renamed"
    KICKED = "kicked"
    WAVE_STARTED = "wave_started"
    WAVE_REPLACED = "wave_replaced"
    WAVE_STOPPED = "wave_stopped"
    WAVE_UNAVAILABLE = "wave_unavailable"
    WAVE_RESUMED = "wave_resumed"
    TRACK_LIKED = "track_liked"


class WaveStopReason(StrEnum):
    USER = "user"
    OWNER_AWAY = "owner_away"
    OWNER_GONE = "owner_gone"
    AUTH = "auth"


class RoomEvent(ApiModel):
    id: str
    at_ms: int
    kind: EventKind
    user_id: str | None = None
    user_name: str | None = None
    count: int | None = None
    title: str | None = None
    position_ms: int | None = None
    repeat: RepeatMode | None = None
    source: QueueSource | None = None
    reason: WaveStopReason | None = None


class ChatMessage(ApiModel):
    id: str
    at_ms: int
    user_id: str
    user_name: str
    text: str | None = None
    emoji: str | None = None
    track_id: str | None = None


class TrackLikes(ApiModel):
    """Кто лайкнул текущий элемент очереди в этой комнате."""

    queue_item_id: str | None = None
    user_ids: list[str] = []


class Pong(ApiModel):
    type: Literal["pong"] = "pong"
    t0: float
    server_time: float


class Snapshot(ApiModel):
    type: Literal["snapshot"] = "snapshot"
    server_time: float
    self_user_id: str
    room: RoomInfo
    playback: PlaybackState
    queue: QueueState
    members: list[MemberView]
    stats: SyncStats
    events: list[RoomEvent]
    chat: list[ChatMessage]
    wave: WaveView = WaveView()
    track_likes: TrackLikes = TrackLikes()


class PlaybackMessage(ApiModel):
    type: Literal["playback"] = "playback"
    state: PlaybackState


class QueueMessage(ApiModel):
    type: Literal["queue"] = "queue"
    queue: QueueState


class MembersMessage(ApiModel):
    type: Literal["members"] = "members"
    members: list[MemberView]
    stats: SyncStats


class WaveMessage(ApiModel):
    type: Literal["wave"] = "wave"
    wave: WaveView


class TrackLikesMessage(ApiModel):
    type: Literal["track_likes"] = "track_likes"
    likes: TrackLikes


class RoomInfoMessage(ApiModel):
    type: Literal["room"] = "room"
    room: RoomInfo


class EventMessage(ApiModel):
    type: Literal["event"] = "event"
    event: RoomEvent


class ChatMessageEnvelope(ApiModel):
    type: Literal["chat"] = "chat"
    message: ChatMessage


class Ack(ApiModel):
    type: Literal["ack"] = "ack"
    client_msg_id: str


class ErrorMessage(ApiModel):
    type: Literal["error"] = "error"
    client_msg_id: str | None = None
    code: str
    message: str


class CloseReason(StrEnum):
    DELETED = "deleted"
    KICKED = "kicked"
    RESTART = "restart"
    REPLACED = "replaced"


class Closed(ApiModel):
    """Сервер закрывает соединение: комната удалена, участника выгнали, сервер перезапускается."""

    type: Literal["closed"] = "closed"
    reason: CloseReason


ServerMessage = Annotated[
    Pong
    | Snapshot
    | PlaybackMessage
    | QueueMessage
    | MembersMessage
    | RoomInfoMessage
    | EventMessage
    | ChatMessageEnvelope
    | WaveMessage
    | TrackLikesMessage
    | Ack
    | ErrorMessage
    | Closed,
    Field(discriminator="type"),
]
server_message_adapter: TypeAdapter[ServerMessage] = TypeAdapter(ServerMessage)

# Коды закрытия WebSocket (4000–4999 — прикладные).
WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_FORBIDDEN = 4403
WS_CLOSE_NOT_FOUND = 4404
WS_CLOSE_RECONNECT = 4012
"""«Переподключитесь»: сервер перезапускается (graceful shutdown)."""
