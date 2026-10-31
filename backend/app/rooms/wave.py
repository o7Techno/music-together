"""Волна комнаты: чистая логика без I/O (SPEC-wave §4). Запросы к Яндексу — в `wave_driver.py`.

Волна — источник автопродолжения: будущие треки лежат в буфере, а не в `Queue.upcoming`, поэтому
перемешивание и очистка очереди её не трогают, а очередь не раздувается в рассылках.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from app.core.schema import ApiModel
from app.providers.base import Track
from app.rooms.queue import QueueItem, QueueOrigin, make_item

WAVE_BUFFER_MIN = 3
WAVE_PREVIEW = 5
WAVE_RECENT_LIMIT = 100
OWNER_GRACE_MS = 15 * 60 * 1000
SETTINGS_DEBOUNCE_MS = 2000
RETRY_DELAYS_MS = (5_000, 15_000, 60_000, 120_000)
MY_WAVE_SEED = "user:onyourwave"


class WaveMode(StrEnum):
    PERSONAL = "personal"
    SEED = "seed"


class WaveStatus(StrEnum):
    OFF = "off"
    STARTING = "starting"
    PLAYING = "playing"
    WAITING = "waiting"
    """Буфер пуст и очередь пуста: ждём порцию."""
    UNAVAILABLE = "unavailable"
    """Яндекс не отдаёт треки: повторяем с паузами."""


class WaveMix(StrEnum):
    MANUAL_FIRST = "manual_first"
    ALTERNATE = "alternate"


class RoomSettings(ApiModel):
    wave_mix: WaveMix = WaveMix.MANUAL_FIRST
    announce_likes: bool = True


class WaveSeed(ApiModel):
    """Зерно волны. Сид для API собирает сервер: сырую строку от клиента в Яндекс не передаём."""

    kind: Literal["track", "artist", "album", "genre", "mood", "activity"]
    id: str = Field(pattern=r"^[\w-]{1,64}$")
    label: str = Field(min_length=1, max_length=80)

    @property
    def api_seed(self) -> str:
        return f"{self.kind}:{self.id}"


class WaveMeta(ApiModel):
    """Откуда пришёл элемент. Только на сервере: очередь рассылается клиентам целиком."""

    session_id: str
    batch_id: str | None = None
    owner_id: str
    track_id: str


class WaveState(ApiModel):
    """Сохраняемое состояние волны: уходит в `rooms.state`, клиентам — только `WaveView`."""

    version: int = 0
    generation: int = 0
    """Растёт при старте, замене, остановке и смене настроек: поздние ответы отбрасываются."""
    wave_id: str | None = None
    status: WaveStatus = WaveStatus.OFF
    mode: WaveMode | None = None
    owner_id: str | None = None
    owner_name: str | None = None
    owner_left_at_ms: int | None = None
    seed: WaveSeed | None = None
    settings: list[str] = []
    session_id: str | None = None
    buffer: list[QueueItem] = []
    meta: dict[str, WaveMeta] = {}
    recent_track_ids: list[str] = []
    tracked_item_id: str | None = None
    """Элемент волны, для которого отправлен `trackStarted`."""
    played_ms: int = 0
    last_from_wave: bool = False


class WaveView(ApiModel):
    version: int = 0
    wave_id: str | None = None
    status: WaveStatus = WaveStatus.OFF
    mode: WaveMode | None = None
    owner_id: str | None = None
    owner_name: str | None = None
    owner_away: bool = False
    seed_label: str | None = None
    settings: list[str] = []
    next: list[QueueItem] = []
    next_track_id: str | None = None
    """Что заиграет следующим по решению сервера: клиент предзагружает именно это."""


def is_active(state: WaveState) -> bool:
    return state.status is not WaveStatus.OFF


def api_seeds(state: WaveState) -> list[str]:
    base = state.seed.api_seed if state.seed is not None else MY_WAVE_SEED
    return [base, *state.settings]


def origin_for(state: WaveState) -> QueueOrigin:
    return QueueOrigin(
        kind="wave",
        owner_id=state.owner_id,
        owner_name=state.owner_name,
        seed_label=state.seed.label if state.seed is not None else None,
    )


def remember_recent(state: WaveState, track_id: str) -> None:
    if track_id in state.recent_track_ids:
        state.recent_track_ids.remove(track_id)
    state.recent_track_ids.append(track_id)
    del state.recent_track_ids[:-WAVE_RECENT_LIMIT]


def accept_batch(
    state: WaveState,
    tracks: list[Track],
    *,
    session_id: str,
    batch_id: str | None,
    queued_track_ids: set[str],
    now_ms: int,
) -> int:
    """Положить порцию в буфер без повторов. Возвращает, сколько треков принято."""
    owner_id = state.owner_id or ""
    origin = origin_for(state)
    seen = set(state.recent_track_ids) | queued_track_ids
    accepted = 0
    for track in tracks:
        if track.id in seen:
            continue
        seen.add(track.id)
        item = make_item(track, owner_id, now_ms).model_copy(update={"origin": origin})
        state.buffer.append(item)
        state.meta[item.id] = WaveMeta(
            session_id=session_id, batch_id=batch_id, owner_id=owner_id, track_id=track.id
        )
        remember_recent(state, track.id)
        accepted += 1
    return accepted


def takes_from_wave(state: WaveState, *, upcoming_count: int, mix: WaveMix) -> bool:
    """Следующий трек — из волны? Ручная очередь приоритетна, в режиме «через один» — чередуем."""
    if not is_active(state) or not state.buffer:
        return False
    if upcoming_count == 0:
        return True
    return mix is WaveMix.ALTERNATE and not state.last_from_wave


def needs_refill(state: WaveState) -> bool:
    return is_active(state) and len(state.buffer) < WAVE_BUFFER_MIN


def prune_meta(state: WaveState, keep: set[str]) -> None:
    """Метаданные нужны только текущему элементу и буферу."""
    alive = keep | {i.id for i in state.buffer}
    for item_id in [k for k in state.meta if k not in alive]:
        del state.meta[item_id]
