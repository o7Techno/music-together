"""Авторитетное состояние воспроизведения (SPEC §5.2)."""

from __future__ import annotations

from enum import StrEnum

from app.core.schema import ApiModel


class PlaybackStatus(StrEnum):
    PLAYING = "playing"
    PAUSED = "paused"
    LOADING = "loading"


class PlaybackState(ApiModel):
    queue_item_id: str | None = None
    track_id: str | None = None
    status: PlaybackStatus = PlaybackStatus.PAUSED
    position_ms: int = 0
    """Позиция в момент `anchor_server_ms`."""
    anchor_server_ms: int = 0
    duration_ms: int = 0
    version: int = 0
    updated_by: str | None = None


def expected_position_ms(state: PlaybackState, server_now_ms: int) -> int:
    """Где должен быть трек в момент `server_now_ms`.

    До момента якоря (старт назначен в будущем) позиция не двигается;
    результат ограничен длительностью.
    """
    if state.status is not PlaybackStatus.PLAYING:
        return state.position_ms
    elapsed = max(0, server_now_ms - state.anchor_server_ms)
    position = state.position_ms + elapsed
    if state.duration_ms > 0:
        position = min(position, state.duration_ms)
    return position


def remaining_ms(state: PlaybackState, server_now_ms: int) -> int:
    """Сколько осталось до конца трека (с учётом старта в будущем)."""
    if state.status is not PlaybackStatus.PLAYING or state.duration_ms <= 0:
        return 0
    start_delay = max(0, state.anchor_server_ms - server_now_ms)
    return start_delay + state.duration_ms - expected_position_ms(state, server_now_ms)
