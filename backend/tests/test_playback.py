from app.rooms.playback import (
    PlaybackState,
    PlaybackStatus,
    expected_position_ms,
    remaining_ms,
)


def state(**kw: object) -> PlaybackState:
    base: dict[str, object] = {
        "queue_item_id": "q1",
        "track_id": "t1",
        "status": PlaybackStatus.PLAYING,
        "position_ms": 10_000,
        "anchor_server_ms": 1_000_000,
        "duration_ms": 60_000,
    }
    return PlaybackState.model_validate(base | kw)


def test_paused_position_is_frozen() -> None:
    s = state(status=PlaybackStatus.PAUSED)
    assert expected_position_ms(s, 1_000_000) == 10_000
    assert expected_position_ms(s, 9_999_999) == 10_000


def test_loading_position_is_frozen() -> None:
    assert expected_position_ms(state(status=PlaybackStatus.LOADING), 1_005_000) == 10_000


def test_playing_position_advances_from_anchor() -> None:
    s = state()
    assert expected_position_ms(s, 1_000_000) == 10_000
    assert expected_position_ms(s, 1_002_500) == 12_500


def test_future_anchor_holds_position_until_start() -> None:
    s = state(anchor_server_ms=1_000_300)
    assert expected_position_ms(s, 1_000_000) == 10_000
    assert expected_position_ms(s, 1_000_400) == 10_100


def test_position_is_clamped_to_duration() -> None:
    assert expected_position_ms(state(), 1_000_000 + 999_999) == 60_000


def test_remaining_includes_start_delay() -> None:
    s = state(anchor_server_ms=1_000_300)
    assert remaining_ms(s, 1_000_000) == 300 + 50_000
    assert remaining_ms(state(), 1_010_000) == 40_000
    assert remaining_ms(state(status=PlaybackStatus.PAUSED), 1_000_000) == 0
