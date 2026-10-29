"""Переходы состояния комнаты, барьер готовности, антидребезг команд (SPEC §5.4, §5.7)."""

from __future__ import annotations

import pytest

from app.core.clock import FakeClock
from app.core.errors import ConflictError, RateLimitedError, ValidationError
from app.rooms.playback import PlaybackState, PlaybackStatus, expected_position_ms
from app.rooms.queue import RepeatMode
from app.rooms.room import (
    BARRIER_TIMEOUT_MS,
    LEAVE_GRACE_MS,
    RESUME_LEAD_MS,
    SEEK_BARRIER_TIMEOUT_MS,
    SEEK_LEAD_MS,
    START_LEAD_MS,
    Room,
    RoomUser,
)
from app.rooms.timers import FakeTimers
from app.ws.protocol import (
    AddPosition,
    ClientStatus,
    CmdNext,
    CmdPause,
    CmdPlay,
    CmdPlayItem,
    CmdPrev,
    CmdSeek,
    CmdSetRepeat,
    DriftReport,
    EventKind,
    PlaybackMessage,
    QueueRemove,
    Ready,
)
from tests.factories import RecordingOutbox, track

ANNA = RoomUser(id="u1", name="Аня")
PETYA = RoomUser(id="u2", name="Петя")


class Env:
    def __init__(self) -> None:
        self.clock = FakeClock()
        self.timers = FakeTimers(self.clock)
        self.out = RecordingOutbox()
        self.changes = 0
        self.room = Room(
            room_id="r1",
            slug="room",
            name="Комната",
            owner_id=ANNA.id,
            clock=self.clock,
            timers=self.timers,
            outbox=self.out,
            on_change=self._on_change,
        )
        self._msg = 0

    def _on_change(self, _room: Room) -> None:
        self.changes += 1

    def mid(self) -> str:
        self._msg += 1
        return f"m{self._msg}"

    async def join(self, conn: str, user: RoomUser, *, unlocked: bool = True) -> None:
        await self.room.join(conn, user)
        await self.room.update_client_status(conn, ClientStatus(audio_unlocked=unlocked))

    async def add(self, conn: str, *ns: int, position: AddPosition = AddPosition.END) -> None:
        await self.room.add_tracks(
            conn,
            self.mid(),
            [track(n) for n in ns],
            position=position,
            index=None,
            source=None,
        )

    async def ready_all(self, *conns: str) -> None:
        for conn in conns:
            await self.room.ready(conn, Ready(version=self.room.playback.version))

    def status(self) -> PlaybackStatus:
        return self.room.playback.status

    @property
    def pb(self) -> PlaybackState:
        return self.room.playback


@pytest.fixture
def env() -> Env:
    return Env()


async def test_first_add_starts_loading_with_barrier(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.add("c1", 1, 2)
    assert env.status() is PlaybackStatus.LOADING
    assert env.pb.track_id == "t1"
    assert env.room.queue.current is not None
    assert [i.track.id for i in env.room.queue.upcoming] == ["t2"]


async def test_barrier_waits_for_all_unlocked_clients(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.join("c2", PETYA)
    await env.join("c3", RoomUser(id="u3", name="Без звука"), unlocked=False)
    await env.add("c1", 1)
    version = env.pb.version

    await env.room.ready("c1", Ready(version=version))
    assert env.status() is PlaybackStatus.LOADING  # ждём c2; c3 не разблокирован — не ждём

    await env.room.ready("c2", Ready(version=version))
    assert env.status() is PlaybackStatus.PLAYING
    assert env.pb.anchor_server_ms == env.clock.now_ms() + START_LEAD_MS
    assert env.pb.position_ms == 0
    assert env.pb.version == version + 1


async def test_ready_for_stale_version_is_ignored(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.add("c1", 1)
    await env.room.ready("c1", Ready(version=env.pb.version - 1))
    assert env.status() is PlaybackStatus.LOADING


async def test_barrier_times_out(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.join("c2", PETYA)
    await env.add("c1", 1)
    await env.ready_all("c1")
    await env.timers.advance(BARRIER_TIMEOUT_MS - 1)
    assert env.status() is PlaybackStatus.LOADING
    await env.timers.advance(1)
    assert env.status() is PlaybackStatus.PLAYING
    assert env.pb.anchor_server_ms == env.clock.now_ms() + START_LEAD_MS


async def test_no_eligible_clients_starts_immediately(env: Env) -> None:
    await env.join("c1", ANNA, unlocked=False)
    await env.add("c1", 1)
    assert env.status() is PlaybackStatus.PLAYING


async def test_disconnect_during_barrier_releases_it(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.join("c2", PETYA)
    await env.add("c1", 1)
    await env.ready_all("c1")
    await env.room.leave("c2")
    assert env.status() is PlaybackStatus.PLAYING


async def test_track_unavailable_client_not_awaited(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.join("c2", PETYA)
    await env.add("c1", 1)
    await env.room.update_client_status(
        "c2", ClientStatus(audio_unlocked=True, track_unavailable=True)
    )
    await env.ready_all("c1")
    assert env.status() is PlaybackStatus.PLAYING


async def test_server_advances_on_track_end_timer(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.add("c1", 1, 2)
    await env.ready_all("c1")
    first_item = env.pb.queue_item_id
    await env.timers.advance(START_LEAD_MS + 60_000 - 1)
    assert env.pb.queue_item_id == first_item
    await env.timers.advance(1)
    assert env.pb.track_id == "t2"
    assert env.status() is PlaybackStatus.LOADING


async def test_queue_end_stops_playback(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.add("c1", 1)
    await env.ready_all("c1")
    await env.timers.advance(START_LEAD_MS + 60_000)
    assert env.pb.queue_item_id is None
    assert env.status() is PlaybackStatus.PAUSED
    assert env.room.queue.history[0].track.id == "t1"


async def test_repeat_track_restarts_same_item(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.add("c1", 1, 2)
    await env.room.handle("c1", CmdSetRepeat(client_msg_id="x", mode=RepeatMode.TRACK))
    await env.ready_all("c1")
    item_id = env.pb.queue_item_id
    await env.timers.advance(START_LEAD_MS + 60_000)
    assert env.pb.queue_item_id == item_id
    assert env.status() is PlaybackStatus.LOADING


async def test_pause_freezes_expected_position_and_play_schedules_future_start(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.add("c1", 1)
    await env.ready_all("c1")
    await env.timers.advance(START_LEAD_MS + 5_000)
    await env.room.handle("c1", CmdPause(client_msg_id=env.mid()))
    assert env.status() is PlaybackStatus.PAUSED
    assert env.pb.position_ms == 5_000

    await env.timers.advance(10_000)
    await env.room.handle("c1", CmdPlay(client_msg_id=env.mid()))
    assert env.status() is PlaybackStatus.PLAYING
    assert env.pb.position_ms == 5_000
    assert env.pb.anchor_server_ms == env.clock.now_ms() + RESUME_LEAD_MS
    # Конец трека пересчитан от нового якоря.
    await env.timers.advance(RESUME_LEAD_MS + 55_000 - 1)
    assert env.pb.track_id == "t1"


async def test_pause_before_anchor_keeps_start_position(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.add("c1", 1)
    await env.ready_all("c1")
    await env.timers.advance(100)  # старт назначен на +300 мс
    await env.room.handle("c1", CmdPause(client_msg_id=env.mid()))
    assert env.pb.position_ms == 0


async def test_seek_while_playing_uses_short_barrier(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.join("c2", PETYA)
    await env.add("c1", 1)
    await env.ready_all("c1", "c2")
    item_id = env.pb.queue_item_id
    await env.room.handle(
        "c1", CmdSeek(client_msg_id=env.mid(), position_ms=30_000, expected_queue_item_id=item_id)
    )
    assert env.status() is PlaybackStatus.LOADING
    assert env.pb.position_ms == 30_000
    await env.ready_all("c1")
    await env.timers.advance(SEEK_BARRIER_TIMEOUT_MS)
    assert env.status() is PlaybackStatus.PLAYING
    assert env.pb.anchor_server_ms == env.clock.now_ms() + SEEK_LEAD_MS
    assert env.pb.position_ms == 30_000


async def test_seek_while_paused_just_moves(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.add("c1", 1)
    await env.ready_all("c1")
    await env.room.handle("c1", CmdPause(client_msg_id=env.mid()))
    await env.room.handle(
        "c1",
        CmdSeek(
            client_msg_id=env.mid(),
            position_ms=999_999,
            expected_queue_item_id=env.pb.queue_item_id,
        ),
    )
    assert env.status() is PlaybackStatus.PAUSED
    assert env.pb.position_ms == 60_000 - 500  # ограничено длительностью


async def test_double_next_skips_only_one_track(env: Env) -> None:
    """Два участника одновременно жмут «следующий» с одним и тем же expectedQueueItemId."""
    await env.join("c1", ANNA)
    await env.join("c2", PETYA)
    await env.add("c1", 1, 2, 3)
    current = env.pb.queue_item_id

    await env.room.handle("c1", CmdNext(client_msg_id=env.mid(), expected_queue_item_id=current))
    with pytest.raises(ConflictError):
        await env.room.handle(
            "c2", CmdNext(client_msg_id=env.mid(), expected_queue_item_id=current)
        )
    assert env.pb.track_id == "t2"
    assert [i.track.id for i in env.room.queue.upcoming] == ["t3"]


async def test_stale_seek_rejected(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.add("c1", 1, 2)
    with pytest.raises(ConflictError):
        await env.room.handle(
            "c1", CmdSeek(client_msg_id=env.mid(), position_ms=1000, expected_queue_item_id="old")
        )


async def test_prev_restarts_after_3s_else_goes_back(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.add("c1", 1, 2)
    await env.ready_all("c1")
    await env.room.handle(
        "c1", CmdNext(client_msg_id=env.mid(), expected_queue_item_id=env.pb.queue_item_id)
    )
    await env.ready_all("c1")
    await env.timers.advance(START_LEAD_MS + 5_000)
    # > 3 с — в начало текущего
    await env.room.handle(
        "c1", CmdPrev(client_msg_id=env.mid(), expected_queue_item_id=env.pb.queue_item_id)
    )
    assert env.pb.track_id == "t2"
    assert env.pb.position_ms == 0
    await env.ready_all("c1")
    await env.timers.advance(SEEK_LEAD_MS + 1_000)
    # < 3 с — предыдущий из истории
    await env.room.handle(
        "c1", CmdPrev(client_msg_id=env.mid(), expected_queue_item_id=env.pb.queue_item_id)
    )
    assert env.pb.track_id == "t1"
    assert [i.track.id for i in env.room.queue.upcoming] == ["t2"]


async def test_play_item_and_play_now(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.add("c1", 1, 2, 3)
    target = env.room.queue.upcoming[1]
    await env.room.handle("c1", CmdPlayItem(client_msg_id=env.mid(), queue_item_id=target.id))
    assert env.pb.queue_item_id == target.id
    await env.add("c1", 9, position=AddPosition.NOW)
    assert env.pb.track_id == "t9"
    assert env.status() in (PlaybackStatus.LOADING, PlaybackStatus.PLAYING)


async def test_play_on_empty_queue_is_validation_error(env: Env) -> None:
    await env.join("c1", ANNA)
    with pytest.raises(ValidationError):
        await env.room.handle("c1", CmdPlay(client_msg_id=env.mid()))


async def test_commands_are_acked(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.add("c1", 1, 2)
    msg_id = env.mid()
    await env.room.handle(
        "c1", QueueRemove(client_msg_id=msg_id, item_id=env.room.queue.upcoming[0].id)
    )
    acks = [m for m in env.out.of_type("c1", "ack") if getattr(m, "client_msg_id", None) == msg_id]
    assert len(acks) == 1


async def test_rate_limit_per_user(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.add("c1", 1)
    rejected = 0
    for _ in range(50):
        try:
            await env.room.handle("c1", CmdSetRepeat(client_msg_id=env.mid(), mode=RepeatMode.OFF))
        except RateLimitedError:
            rejected += 1
    assert rejected > 30


async def test_versions_strictly_increase_in_broadcasts(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.add("c1", 1, 2)
    await env.ready_all("c1")
    await env.room.handle("c1", CmdPause(client_msg_id=env.mid()))
    await env.room.handle("c1", CmdPlay(client_msg_id=env.mid()))
    versions = [m.state.version for m in env.out.sent["c1"] if isinstance(m, PlaybackMessage)]
    assert versions == sorted(versions)
    assert len(set(versions)) == len(versions)


async def test_last_leave_pauses_and_persisted_state_is_paused(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.add("c1", 1)
    await env.ready_all("c1")
    await env.timers.advance(START_LEAD_MS + 7_000)
    assert env.room.persisted_playback().status is PlaybackStatus.PAUSED
    assert env.room.persisted_playback().position_ms == 7_000
    await env.room.leave("c1")
    assert env.status() is PlaybackStatus.PAUSED
    assert expected_position_ms(env.pb, env.clock.now_ms()) == 7_000


async def test_join_leave_events_debounced(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.room.leave("c1")
    await env.timers.advance(1000)
    await env.join("c2", ANNA)  # быстрый реконнект — без «вышла/зашла»
    kinds = [e.kind for e in env.room.events]
    assert kinds == [EventKind.JOINED]
    await env.room.leave("c2")
    await env.timers.advance(LEAVE_GRACE_MS)
    assert [e.kind for e in env.room.events] == [EventKind.JOINED, EventKind.LEFT]


async def test_drift_stats_in_members(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.join("c2", PETYA)
    await env.add("c1", 1)
    await env.ready_all("c1", "c2")
    for d in (5, 10, 15, 20, 100):
        await env.room.report_drift("c1", DriftReport(drift_ms=d))
        await env.room.report_drift("c2", DriftReport(drift_ms=-d))
    members, stats = env.room._members_view()
    assert stats.samples == 10
    assert stats.median_ms == 15
    assert all(m.drift_median_ms == 15 for m in members)
    env.out.clear()
    await env.timers.advance(3000)
    assert env.out.of_type("c1", "members")


async def test_kick_closes_all_user_connections(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.join("c2", PETYA)
    await env.join("c3", PETYA)
    env.room.kick(PETYA.id, ANNA)
    assert set(env.out.closed) == {"c2", "c3"}
