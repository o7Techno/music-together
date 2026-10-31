"""Волна комнаты: чистая логика без I/O (SPEC-wave §4). Запросы к Яндексу — в `wave_driver.py`.

Волна — источник автопродолжения: будущие треки лежат в буфере, а не в `Queue.upcoming`, поэтому
перемешивание и очистка очереди её не трогают, а очередь не раздувается в рассылках.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import ConfigDict, Field

from app.core.schema import ApiModel
from app.providers.base import Track
from app.rooms.queue import QueueItem, QueueOrigin, make_item

WAVE_BUFFER_MIN = 3
SHARED_SOURCE_MIN = 2
WAVE_PREVIEW = 5
WAVE_RECENT_LIMIT = 100
OWNER_GRACE_MS = 15 * 60 * 1000
SETTINGS_DEBOUNCE_MS = 2000
RETRY_DELAYS_MS = (5_000, 15_000, 60_000, 120_000)
MY_WAVE_SEED = "user:onyourwave"


class WaveMode(StrEnum):
    PERSONAL = "personal"
    SEED = "seed"
    SHARED = "shared"


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

    # Снимок другой версии кода не должен терять комнату: лишние поля просто забываем.
    model_config = ConfigDict(extra="ignore")

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
    sessions: dict[str, str] = {}
    """Пользователь → его сессия ротора. Без режима общей волны запись одна."""
    opted_out: list[str] = []
    """Кто выключил «Моя волна участвует». Переживает остановку волны."""
    last_source_id: str | None = None
    """Чей трек волны взят последним: с кого продолжать круг."""
    buffer: list[QueueItem] = []
    meta: dict[str, WaveMeta] = {}
    recent_track_ids: list[str] = []
    tracked_item_id: str | None = None
    """Элемент волны, для которого отправлен `trackStarted`."""
    played_ms: int = 0
    last_from_wave: bool = False


class WaveSourceView(ApiModel):
    user_id: str
    name: str
    enabled: bool
    """Переключатель «Моя волна участвует»."""
    active: bool
    """Сейчас в ротации: включено, онлайн, звук разблокирован, есть Плюс."""


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
    sources: list[WaveSourceView] = []
    next: list[QueueItem] = []
    next_track_id: str | None = None
    """Что заиграет следующим по решению сервера: клиент предзагружает именно это."""


def is_active(state: WaveState) -> bool:
    return state.status is not WaveStatus.OFF


def api_seeds(state: WaveState) -> list[str]:
    base = state.seed.api_seed if state.seed is not None else MY_WAVE_SEED
    return [base, *state.settings]


def origin_for(state: WaveState, owner_id: str, owner_name: str | None) -> QueueOrigin:
    return QueueOrigin(
        kind="wave",
        owner_id=owner_id,
        owner_name=owner_name,
        seed_label=state.seed.label if state.seed is not None else None,
        shared=state.mode is WaveMode.SHARED,
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
    owner_id: str,
    owner_name: str | None,
    session_id: str,
    batch_id: str | None,
    queued_track_ids: set[str],
    now_ms: int,
) -> int:
    """Положить порцию в буфер без повторов. Возвращает, сколько треков принято."""
    origin = origin_for(state, owner_id, owner_name)
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


def needs_refill(state: WaveState, source_id: str, source_count: int = 1) -> bool:
    """Мало треков этого источника. В общей волне буфер делится между источниками."""
    if not is_active(state):
        return False
    have = sum(1 for item in state.buffer if item.added_by == source_id)
    wanted = WAVE_BUFFER_MIN if source_count <= 1 else SHARED_SOURCE_MIN
    return have < wanted


def round_robin(state: WaveState, source_ids: list[str]) -> None:
    """Выстроить буфер по кругу: начиная с источника после того, чей трек взят последним.

    Порядок внутри источника сохраняется; у кого треки кончились, тот пропускает свою очередь.
    """
    if len(source_ids) <= 1:
        return
    if state.last_source_id in source_ids:
        start = source_ids.index(state.last_source_id) + 1
        source_ids = source_ids[start:] + source_ids[:start]
    pending = {source: [i for i in state.buffer if i.added_by == source] for source in source_ids}
    merged: list[QueueItem] = []
    while any(pending.values()):
        for source in source_ids:
            if pending[source]:
                merged.append(pending[source].pop(0))
    state.buffer = merged


def drop_sources_except(state: WaveState, source_ids: set[str]) -> None:
    """Выпавшие источники: их будущие треки убираем, текущий трек доигрывает."""
    for item in [i for i in state.buffer if i.added_by not in source_ids]:
        state.buffer.remove(item)
        state.meta.pop(item.id, None)


def prune_meta(state: WaveState, keep: set[str]) -> None:
    """Метаданные нужны только текущему элементу и буферу."""
    alive = keep | {i.id for i in state.buffer}
    for item_id in [k for k in state.meta if k not in alive]:
        del state.meta[item_id]
