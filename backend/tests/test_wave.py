"""Волна в акторе комнаты на FakeClock/FakeTimers: выбор следующего, буфер, фидбек, уход."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.core.clock import FakeClock
from app.core.errors import ConflictError, ForbiddenError, ValidationError
from app.providers.base import (
    SubscriptionRequiredError,
    WaveBatch,
    WaveFeedback,
    WaveFeedbackKind,
)
from app.rooms.playback import PlaybackStatus
from app.rooms.queue import QueueState, RepeatMode
from app.rooms.room import Room, RoomUser
from app.rooms.timers import FakeTimers
from app.rooms.wave import (
    RETRY_DELAYS_MS,
    SETTINGS_DEBOUNCE_MS,
    RoomSettings,
    WaveMix,
    WaveMode,
    WaveSeed,
    WaveState,
    WaveStatus,
)
from app.rooms.wave_driver import WaveRequest
from app.ws.protocol import (
    AddPosition,
    ClientStatus,
    CloseReason,
    CmdNext,
    CmdPause,
    CmdPlay,
    CmdPlayItem,
    CmdPrev,
    CmdSeek,
    CmdSetRepeat,
    EventKind,
    Ready,
    TrackDislike,
    WaveMessage,
    WavePin,
    WaveRemove,
    WaveStart,
    WaveStop,
    WaveStopReason,
    WaveUpdateSettings,
)
from tests.factories import RecordingOutbox, track

ANNA = RoomUser(id="u1", name="Аня")
PETYA = RoomUser(id="u2", name="Петя")
GRACE_MS = 60_000


@dataclass
class FakeDriver:
    requests: list[WaveRequest] = field(default_factory=list)
    events: list[tuple[str, str, WaveFeedback]] = field(default_factory=list)
    dislikes: list[tuple[str, str]] = field(default_factory=list)

    def request_batch(self, room: Room, request: WaveRequest) -> None:
        self.requests.append(request)

    def feedback(self, user_id: str, session_id: str, event: WaveFeedback) -> None:
        self.events.append((user_id, session_id, event))

    def dislike(self, user_id: str, track_id: str) -> None:
        self.dislikes.append((user_id, track_id))

    def kinds(self) -> list[WaveFeedbackKind]:
        return [e.kind for _, _, e in self.events]

    def last(self, kind: WaveFeedbackKind) -> WaveFeedback:
        return [e for _, _, e in self.events if e.kind is kind][-1]


class Env:
    def __init__(
        self,
        *,
        wave: WaveState | None = None,
        mix: WaveMix | None = None,
        queue: QueueState | None = None,
    ) -> None:
        self.clock = FakeClock()
        self.timers = FakeTimers(self.clock)
        self.out = RecordingOutbox()
        self.driver = FakeDriver()
        self.number = 0
        self.room = Room(
            room_id="r1",
            slug="room",
            name="Комната",
            owner_id=ANNA.id,
            clock=self.clock,
            timers=self.timers,
            outbox=self.out,
            queue=queue,
            wave=wave,
            settings=RoomSettings(wave_mix=mix) if mix else None,
            wave_driver=self.driver,
            owner_grace_ms=GRACE_MS,
        )
        self._msg = 0

    def mid(self) -> str:
        self._msg += 1
        return f"m{self._msg}"

    async def join(self, conn: str, user: RoomUser) -> None:
        await self.room.join(conn, user)
        await self.room.update_client_status(conn, ClientStatus(audio_unlocked=True))

    async def start(self, conn: str = "c1") -> None:
        await self.room.handle(conn, WaveStart(client_msg_id=self.mid(), mode=WaveMode.PERSONAL))

    async def batch(self, count: int = 5, *, generation: int | None = None) -> list[str]:
        ids = []
        for _ in range(count):
            self.number += 1
            ids.append(f"w{self.number}")
        await self.room.apply_wave_batch(
            self.room.wave.generation if generation is None else generation,
            WaveBatch(
                session_id="s1",
                batch_id=f"b{self.number}",
                tracks=[track(i, 60_000) for i in ids],
            ),
        )
        return [f"t{i}" for i in ids]

    async def add(self, conn: str, *ns: int, position: AddPosition = AddPosition.END) -> None:
        await self.room.add_tracks(
            conn, self.mid(), [track(n) for n in ns], position=position, index=None, source=None
        )

    async def play_barrier(self, conn: str = "c1") -> None:
        await self.room.ready(conn, Ready(version=self.room.playback.version))
        assert self.room.playback.status is PlaybackStatus.PLAYING
        await self.timers.advance(300)

    async def next(self, conn: str = "c1") -> None:
        await self.room.handle(
            conn,
            CmdNext(
                client_msg_id=self.mid(), expected_queue_item_id=self.room.playback.queue_item_id
            ),
        )

    def current(self) -> str | None:
        return self.room.playback.track_id

    def status(self) -> WaveStatus:
        return self.room.wave.status

    def events(self) -> list[EventKind]:
        return [e.kind for e in self.room.events]


@pytest.fixture
def env() -> Env:
    return Env()


async def started(env: Env) -> list[str]:
    await env.join("c1", ANNA)
    await env.start()
    return await env.batch()


async def test_wave_starts_playing_without_manual_tracks(env: Env) -> None:
    ids = await started(env)
    assert env.status() is WaveStatus.PLAYING
    assert env.current() == ids[0]
    assert env.room.queue.current is not None
    assert env.room.queue.current.origin.kind == "wave"
    assert env.room.queue.current.added_by == ANNA.id
    assert [i.track.id for i in env.room.wave.buffer] == ids[1:]
    assert env.room.queue.upcoming == []
    assert EventKind.WAVE_STARTED in env.events()


async def test_manual_queue_has_priority_over_wave(env: Env) -> None:
    ids = await started(env)
    await env.play_barrier()
    await env.add("c1", 1, 2)
    await env.next()
    assert env.current() == "t1"
    await env.play_barrier()
    await env.next()
    assert env.current() == "t2"
    await env.play_barrier()
    await env.next()
    assert env.current() == ids[1]


async def test_alternate_mode_takes_tracks_in_turn() -> None:
    env = Env(mix=WaveMix.ALTERNATE)
    ids = await started(env)
    await env.play_barrier()
    await env.add("c1", 1, 2)
    played = []
    for _ in range(4):
        await env.next()
        played.append(env.current())
        await env.play_barrier()
    assert played == ["t1", ids[1], "t2", ids[2]]


async def test_next_track_id_matches_what_actually_plays() -> None:
    env = Env(mix=WaveMix.ALTERNATE)
    await started(env)
    await env.play_barrier()
    await env.add("c1", 1)
    for _ in range(4):
        announced = env.room._next_track_id()
        await env.next()
        assert env.current() == announced
        await env.play_barrier()


async def test_next_track_id_is_broadcast_when_manual_queue_changes(env: Env) -> None:
    await started(env)
    env.out.clear()
    await env.add("c1", 1)
    wave = [m for m in env.out.sent["c1"] if isinstance(m, WaveMessage)]
    assert wave
    assert wave[-1].wave.next_track_id == "t1"


async def test_buffer_changes_do_not_touch_playback_version(env: Env) -> None:
    """Новая версия воспроизведения сбросила бы контроллер дрейфа у всех клиентов."""
    await started(env)
    await env.play_barrier()
    version = env.room.playback.version
    await env.batch()
    item = env.room.wave.buffer[0]
    await env.room.handle("c1", WavePin(client_msg_id=env.mid(), item_id=item.id))
    await env.room.handle(
        "c1", WaveRemove(client_msg_id=env.mid(), item_id=env.room.wave.buffer[0].id)
    )
    await env.room.handle("c1", WaveUpdateSettings(client_msg_id=env.mid(), settings=[]))
    assert env.room.playback.version == version


async def test_second_start_without_expected_id_is_a_conflict(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.start()
    assert len(env.driver.requests) == 1
    with pytest.raises(ConflictError):
        await env.start()


async def test_refill_after_consuming_buffer(env: Env) -> None:
    await started(env)  # 1 играет, в буфере 4
    assert len(env.driver.requests) == 1
    await env.next()  # 3 в буфере
    await env.play_barrier()
    assert len(env.driver.requests) == 1
    await env.next()  # 2 в буфере: ниже порога
    assert len(env.driver.requests) == 2
    await env.play_barrier()
    await env.next()  # запрос уже идёт, второй не нужен
    assert len(env.driver.requests) == 2
    assert env.driver.requests[-1].session_id == "s1"


async def test_late_batch_from_replaced_wave_is_ignored(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.start()
    stale = env.room.wave.generation
    await env.room.handle("c1", WaveStop(client_msg_id=env.mid()))
    await env.batch(generation=stale)
    assert env.room.wave.buffer == []
    assert env.current() is None


async def test_duplicates_and_recent_tracks_are_filtered(env: Env) -> None:
    await started(env)
    before = len(env.room.wave.buffer)
    await env.room.apply_wave_batch(
        env.room.wave.generation,
        WaveBatch(session_id="s1", batch_id="b", tracks=[track("w1"), track("w2"), track("new")]),
    )
    assert len(env.room.wave.buffer) == before + 1
    assert env.room.wave.buffer[-1].track.id == "tnew"


async def test_recent_limit_keeps_last_hundred(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.start()
    for _ in range(25):
        await env.batch(5)
    assert len(env.room.wave.recent_track_ids) == 100
    assert env.room.wave.recent_track_ids[-1] == "tw125"


async def test_empty_batch_is_failure_and_retries_with_backoff(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.start()
    await env.batch(0)
    assert env.status() is WaveStatus.UNAVAILABLE
    assert EventKind.WAVE_UNAVAILABLE in env.events()
    assert len(env.driver.requests) == 1
    await env.timers.advance(RETRY_DELAYS_MS[0])
    assert len(env.driver.requests) == 2
    await env.batch()
    assert env.status() is WaveStatus.PLAYING
    assert EventKind.WAVE_RESUMED in env.events()
    assert env.current() is not None


async def test_failure_with_buffer_keeps_playing_silently(env: Env) -> None:
    await started(env)
    await env.room.apply_wave_failure(env.room.wave.generation, fatal=False)
    assert env.status() is WaveStatus.PLAYING
    assert EventKind.WAVE_UNAVAILABLE not in env.events()


async def test_buffer_exhausted_falls_back_to_manual_then_waits(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.start()
    await env.batch(1)
    await env.play_barrier()
    await env.add("c1", 1)
    await env.next()
    assert env.current() == "t1"
    await env.play_barrier()
    await env.next()
    assert env.current() is None
    assert env.status() is WaveStatus.WAITING
    await env.batch()
    assert env.current() is not None
    assert env.status() is WaveStatus.PLAYING


async def test_fatal_failure_stops_wave_at_once(env: Env) -> None:
    await started(env)
    await env.room.apply_wave_failure(env.room.wave.generation, fatal=True)
    assert env.status() is WaveStatus.OFF
    event = list(env.room.events)[-1]
    assert event.kind is EventKind.WAVE_STOPPED
    assert event.reason is WaveStopReason.AUTH


async def test_stop_lets_current_track_finish_and_clears_buffer(env: Env) -> None:
    ids = await started(env)
    await env.play_barrier()
    await env.room.handle("c1", WaveStop(client_msg_id=env.mid()))
    assert env.current() == ids[0]
    assert env.room.playback.status is PlaybackStatus.PLAYING
    assert env.room.wave.buffer == []
    await env.timers.advance(60_000)
    assert env.current() is None
    assert env.driver.last(WaveFeedbackKind.TRACK_FINISHED).track_id == ids[0]


async def test_play_now_keeps_wave_running(env: Env) -> None:
    ids = await started(env)
    await env.play_barrier()
    await env.add("c1", 1, position=AddPosition.NOW)
    assert env.current() == "t1"
    assert env.status() is WaveStatus.PLAYING
    assert env.driver.last(WaveFeedbackKind.SKIP).track_id == ids[0]
    await env.play_barrier()
    await env.next()
    assert env.current() == ids[1]


async def test_replace_needs_expected_wave_id_and_keeps_current_feedback_route(env: Env) -> None:
    ids = await started(env)
    await env.join("c2", PETYA)
    await env.play_barrier("c1")
    with pytest.raises(ConflictError):
        await env.room.handle("c2", WaveStart(client_msg_id=env.mid(), mode=WaveMode.PERSONAL))
    await env.room.handle(
        "c2",
        WaveStart(
            client_msg_id=env.mid(),
            mode=WaveMode.PERSONAL,
            expected_wave_id=env.room.wave.wave_id,
        ),
    )
    assert env.room.wave.owner_id == PETYA.id
    assert env.room.wave.buffer == []
    assert EventKind.WAVE_REPLACED in env.events()
    await env.room.ready("c2", Ready(version=env.room.playback.version))
    await env.next()
    # Трек прежней волны отчитывается перед её владельцем.
    user, _, event = env.driver.events[-1]
    assert (user, event.kind, event.track_id) == (ANNA.id, WaveFeedbackKind.SKIP, ids[0])


async def test_user_without_plus_cannot_start_wave(env: Env) -> None:
    await env.join("c1", RoomUser(id="u9", name="Без Плюса", can_wave=False))
    with pytest.raises(SubscriptionRequiredError):
        await env.start()


async def test_seed_requires_seed_and_builds_api_seed(env: Env) -> None:
    await env.join("c1", ANNA)
    with pytest.raises(ValidationError):
        await env.room.handle("c1", WaveStart(client_msg_id=env.mid(), mode=WaveMode.SEED))
    await env.room.handle(
        "c1",
        WaveStart(
            client_msg_id=env.mid(),
            mode=WaveMode.SEED,
            seed=WaveSeed(kind="artist", id="42", label="Radiohead"),
            settings=["settingDiversity:discover"],
        ),
    )
    assert env.driver.requests[-1].seeds == ["artist:42", "settingDiversity:discover"]
    await env.batch()
    assert env.room.queue.current is not None
    assert env.room.queue.current.origin.seed_label == "Radiohead"


async def test_repeat_queue_is_reset_and_rejected_while_wave_runs(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.room.handle("c1", CmdSetRepeat(client_msg_id=env.mid(), mode=RepeatMode.QUEUE))
    await env.start()
    assert env.room.queue.repeat is RepeatMode.OFF
    with pytest.raises(ValidationError):
        await env.room.handle("c1", CmdSetRepeat(client_msg_id=env.mid(), mode=RepeatMode.QUEUE))


async def test_repeat_track_holds_wave_and_reports_finish_once(env: Env) -> None:
    ids = await started(env)
    await env.room.handle("c1", CmdSetRepeat(client_msg_id=env.mid(), mode=RepeatMode.TRACK))
    await env.play_barrier()
    await env.timers.advance(60_000)
    assert env.current() == ids[0]
    await env.play_barrier()
    await env.timers.advance(60_000)
    assert env.current() == ids[0]
    assert env.driver.kinds().count(WaveFeedbackKind.TRACK_FINISHED) == 1
    assert env.driver.kinds().count(WaveFeedbackKind.TRACK_STARTED) == 1


async def test_play_with_empty_queue_and_active_wave_does_not_fail(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.start()
    await env.room.handle("c1", CmdPlay(client_msg_id=env.mid()))
    assert env.status() is WaveStatus.STARTING


# ── Фидбек ──────────────────────────────────────────────────────────────────────


async def test_feedback_sequence_on_natural_end(env: Env) -> None:
    ids = await started(env)
    assert env.driver.kinds() == [WaveFeedbackKind.RADIO_STARTED]
    await env.play_barrier()
    assert env.driver.last(WaveFeedbackKind.TRACK_STARTED).track_id == ids[0]
    await env.timers.advance(60_000)
    finished = env.driver.last(WaveFeedbackKind.TRACK_FINISHED)
    assert finished.track_id == ids[0]
    assert finished.played_s == pytest.approx(60, abs=0.5)
    assert finished.batch_id is not None
    assert env.current() == ids[1]


async def test_skip_reports_actual_time_despite_pause_and_seek(env: Env) -> None:
    ids = await started(env)
    await env.play_barrier()  # старт + 300 мс до якоря уже прошли
    await env.timers.advance(10_000)
    await env.room.handle("c1", CmdPause(client_msg_id=env.mid()))
    await env.timers.advance(50_000)  # на паузе время не считается
    await env.room.handle("c1", CmdPlay(client_msg_id=env.mid()))
    await env.timers.advance(5_200)
    await env.room.handle(
        "c1",
        CmdSeek(
            client_msg_id=env.mid(),
            position_ms=50_000,
            expected_queue_item_id=env.room.playback.queue_item_id,
        ),
    )
    await env.room.ready("c1", Ready(version=env.room.playback.version))
    await env.timers.advance(150 + 3_000)
    await env.next()
    skip = env.driver.last(WaveFeedbackKind.SKIP)
    assert skip.track_id == ids[0]
    assert skip.played_s == pytest.approx(18, abs=0.5)
    # Перемотка проходит через тот же барьер, но второго trackStarted нет.
    assert env.driver.kinds().count(WaveFeedbackKind.TRACK_STARTED) == 1


async def test_skip_during_loading_sends_nothing_for_unstarted_track(env: Env) -> None:
    await started(env)
    await env.next()  # первый ни разу не стартовал
    assert WaveFeedbackKind.SKIP not in env.driver.kinds()
    assert WaveFeedbackKind.TRACK_STARTED not in env.driver.kinds()


async def test_manual_tracks_send_no_feedback(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.add("c1", 1, 2)
    await env.play_barrier()
    await env.next()
    assert env.driver.events == []


async def test_prev_sends_skip_and_returning_track_has_no_second_feedback(env: Env) -> None:
    ids = await started(env)
    await env.play_barrier()
    await env.next()
    await env.play_barrier()
    await env.timers.advance(1000)
    await env.room.handle(
        "c1",
        CmdPrev(client_msg_id=env.mid(), expected_queue_item_id=env.room.playback.queue_item_id),
    )
    assert env.current() == ids[0]
    count = env.driver.kinds().count(WaveFeedbackKind.TRACK_STARTED)
    await env.play_barrier()
    assert env.driver.kinds().count(WaveFeedbackKind.TRACK_STARTED) == count


async def test_play_item_interrupting_wave_track_is_a_skip(env: Env) -> None:
    ids = await started(env)
    await env.play_barrier()
    await env.add("c1", 1)
    item = env.room.queue.upcoming[0]
    await env.room.handle("c1", CmdPlayItem(client_msg_id=env.mid(), queue_item_id=item.id))
    assert env.driver.last(WaveFeedbackKind.SKIP).track_id == ids[0]


async def test_pinned_track_is_manual_without_feedback(env: Env) -> None:
    await started(env)
    await env.join("c2", PETYA)
    item = env.room.wave.buffer[0]
    await env.room.handle("c2", WavePin(client_msg_id=env.mid(), item_id=item.id))
    pinned = env.room.queue.upcoming[0]
    assert pinned.track.id == item.track.id
    assert pinned.added_by == PETYA.id
    assert pinned.origin.kind == "manual"
    assert item.track.id not in [i.track.id for i in env.room.wave.buffer]
    await env.room.ready("c1", Ready(version=env.room.playback.version))
    await env.room.ready("c2", Ready(version=env.room.playback.version))
    await env.timers.advance(300)
    await env.next()
    await env.room.ready("c1", Ready(version=env.room.playback.version))
    await env.room.ready("c2", Ready(version=env.room.playback.version))
    assert env.current() == item.track.id
    assert env.driver.kinds().count(WaveFeedbackKind.TRACK_STARTED) == 1


async def test_removed_track_counts_as_skip_without_listening(env: Env) -> None:
    await started(env)
    item = env.room.wave.buffer[1]
    await env.room.handle("c1", WaveRemove(client_msg_id=env.mid(), item_id=item.id))
    skip = env.driver.last(WaveFeedbackKind.SKIP)
    assert skip.track_id == item.track.id
    assert skip.played_s == 0


async def test_dislike_by_owner_goes_to_account_and_skips(env: Env) -> None:
    ids = await started(env)
    await env.play_barrier()
    await env.timers.advance(5_000)
    await env.room.handle(
        "c1",
        TrackDislike(
            client_msg_id=env.mid(), expected_queue_item_id=env.room.playback.queue_item_id
        ),
    )
    assert env.driver.dislikes == [(ANNA.id, ids[0])]
    assert env.driver.last(WaveFeedbackKind.DISLIKE).played_s == pytest.approx(5, abs=0.5)
    assert env.driver.last(WaveFeedbackKind.SKIP).track_id == ids[0]
    assert env.current() == ids[1]


async def test_dislike_by_guest_only_skips(env: Env) -> None:
    ids = await started(env)
    await env.join("c2", PETYA)
    await env.play_barrier()
    await env.room.handle(
        "c2",
        TrackDislike(
            client_msg_id=env.mid(), expected_queue_item_id=env.room.playback.queue_item_id
        ),
    )
    assert env.driver.dislikes == []
    assert WaveFeedbackKind.DISLIKE not in env.driver.kinds()
    assert env.driver.last(WaveFeedbackKind.SKIP).track_id == ids[0]


async def test_dislike_on_manual_track_is_rejected(env: Env) -> None:
    await env.join("c1", ANNA)
    await env.add("c1", 1)
    with pytest.raises(ValidationError):
        await env.room.handle(
            "c1",
            TrackDislike(
                client_msg_id=env.mid(), expected_queue_item_id=env.room.playback.queue_item_id
            ),
        )


# ── Лайки ───────────────────────────────────────────────────────────────────────


async def test_like_of_own_wave_track_sends_feedback_once_in_feed(env: Env) -> None:
    ids = await started(env)
    await env.room.note_like(ANNA, ids[0], liked=True)
    await env.room.note_like(ANNA, ids[0], liked=False)
    await env.room.note_like(ANNA, ids[0], liked=True)
    assert env.room.track_likes.user_ids == [ANNA.id]
    assert env.events().count(EventKind.TRACK_LIKED) == 1
    assert WaveFeedbackKind.LIKE in env.driver.kinds()
    assert WaveFeedbackKind.UNLIKE in env.driver.kinds()


async def test_like_of_someone_elses_wave_sends_no_feedback(env: Env) -> None:
    ids = await started(env)
    await env.join("c2", PETYA)
    await env.room.note_like(PETYA, ids[0], liked=True)
    assert env.room.track_likes.user_ids == [PETYA.id]
    assert WaveFeedbackKind.LIKE not in env.driver.kinds()


async def test_like_counter_resets_with_item_and_ignores_other_tracks(env: Env) -> None:
    ids = await started(env)
    await env.room.note_like(ANNA, "t-other", liked=True)
    assert env.room.track_likes.user_ids == []
    await env.room.note_like(ANNA, ids[0], liked=True)
    await env.next()
    assert env.room.track_likes.user_ids == []


async def test_announce_likes_can_be_disabled(env: Env) -> None:
    ids = await started(env)
    env.room.update_settings(RoomSettings(announce_likes=False))
    await env.room.note_like(ANNA, ids[0], liked=True)
    assert EventKind.TRACK_LIKED not in env.events()
    assert env.room.track_likes.user_ids == [ANNA.id]


# ── Настройки ───────────────────────────────────────────────────────────────────


async def test_settings_change_new_session_after_debounce_and_only_owner(env: Env) -> None:
    ids = await started(env)
    await env.join("c2", PETYA)
    await env.play_barrier("c1")
    with pytest.raises(ForbiddenError):
        await env.room.handle(
            "c2", WaveUpdateSettings(client_msg_id=env.mid(), settings=["settingLanguage:russian"])
        )
    requests = len(env.driver.requests)
    await env.room.handle(
        "c1", WaveUpdateSettings(client_msg_id=env.mid(), settings=["settingLanguage:russian"])
    )
    await env.room.handle(
        "c1", WaveUpdateSettings(client_msg_id=env.mid(), settings=["settingLanguage:any"])
    )
    assert env.room.wave.buffer == []
    assert env.current() == ids[0]
    assert len(env.driver.requests) == requests
    await env.timers.advance(SETTINGS_DEBOUNCE_MS)
    assert len(env.driver.requests) == requests + 1
    request = env.driver.requests[-1]
    assert request.session_id is None
    assert request.seeds == ["user:onyourwave", "settingLanguage:any"]


# ── Уход владельца ──────────────────────────────────────────────────────────────


async def two_listeners(env: Env) -> list[str]:
    await env.join("c1", ANNA)
    await env.join("c2", PETYA)
    await env.start()
    return await env.batch()


async def test_owner_away_stops_wave_after_grace_and_queue_continues(env: Env) -> None:
    await two_listeners(env)
    await env.room.ready("c1", Ready(version=env.room.playback.version))
    await env.room.ready("c2", Ready(version=env.room.playback.version))
    await env.add("c2", 1)
    await env.room.leave("c1")
    assert env.room.wave.owner_left_at_ms is not None
    assert env.room._wave_view().owner_away is True
    await env.timers.advance(GRACE_MS - 1)
    assert env.status() is WaveStatus.PLAYING
    await env.timers.advance(1)
    assert env.status() is WaveStatus.OFF
    event = [e for e in env.room.events if e.kind is EventKind.WAVE_STOPPED][-1]
    assert event.reason is WaveStopReason.OWNER_AWAY
    assert [i.track.id for i in env.room.queue.upcoming] == ["t1"]


async def test_owner_returning_in_time_keeps_wave(env: Env) -> None:
    await two_listeners(env)
    await env.room.leave("c1")
    await env.timers.advance(GRACE_MS - 1000)
    await env.join("c1b", ANNA)
    assert env.room.wave.owner_left_at_ms is None
    await env.timers.advance(GRACE_MS * 2)
    assert env.status() is WaveStatus.PLAYING


async def test_second_connection_of_owner_is_not_leaving(env: Env) -> None:
    await two_listeners(env)
    await env.join("c1b", ANNA)
    await env.room.leave("c1")
    assert env.room.wave.owner_left_at_ms is None


async def test_no_feedback_while_owner_is_away(env: Env) -> None:
    ids = await two_listeners(env)
    await env.room.ready("c1", Ready(version=env.room.playback.version))
    await env.room.ready("c2", Ready(version=env.room.playback.version))
    await env.timers.advance(300)
    before = len(env.driver.events)
    await env.room.leave("c1")
    await env.next("c2")
    assert env.current() == ids[1]
    assert len(env.driver.events) == before


async def test_kicked_owner_stops_wave_at_once(env: Env) -> None:
    await two_listeners(env)
    async with env.room.lock:
        env.room.kick(ANNA.id, PETYA)
    assert env.status() is WaveStatus.OFF


async def test_logout_of_owner_stops_wave_and_other_user_does_not(env: Env) -> None:
    await two_listeners(env)
    await env.room.stop_wave_of(PETYA.id)
    assert env.status() is WaveStatus.PLAYING
    await env.room.stop_wave_of(ANNA.id)
    assert env.status() is WaveStatus.OFF


async def restored(env: Env, left_ago_ms: int | None) -> Env:
    state = env.room.persisted_wave()
    fresh = Env(wave=state, queue=env.room.queue.snapshot())
    fresh.clock.advance(env.clock.now_ms() - fresh.clock.now_ms())
    if left_ago_ms is not None:
        fresh.room.wave.owner_left_at_ms = fresh.clock.now_ms() - left_ago_ms
    return fresh


async def test_grace_survives_restart_and_expired_window_stops_on_first_join(env: Env) -> None:
    await two_listeners(env)
    fresh = await restored(env, left_ago_ms=GRACE_MS + 1)
    await fresh.join("c2", PETYA)
    assert fresh.status() is WaveStatus.OFF


async def test_grace_remainder_is_recalculated_after_restart(env: Env) -> None:
    await two_listeners(env)
    fresh = await restored(env, left_ago_ms=GRACE_MS - 5000)
    await fresh.join("c2", PETYA)
    assert fresh.status() is WaveStatus.PLAYING
    await fresh.timers.advance(4999)
    assert fresh.status() is WaveStatus.PLAYING
    await fresh.timers.advance(1)
    assert fresh.status() is WaveStatus.OFF


async def test_restored_wave_continues_session_without_radio_started(env: Env) -> None:
    await two_listeners(env)
    fresh = await restored(env, left_ago_ms=None)
    await fresh.join("c1", ANNA)
    assert fresh.room.wave.session_id == "s1"
    assert fresh.driver.events == []
    assert fresh.room.wave.buffer


async def test_empty_room_requests_nothing(env: Env) -> None:
    await started(env)
    await env.room.leave("c1")
    requests = len(env.driver.requests)
    await env.room.apply_wave_batch(
        env.room.wave.generation, WaveBatch(session_id="s1", batch_id="b", tracks=[])
    )
    await env.timers.advance(RETRY_DELAYS_MS[0])
    assert len(env.driver.requests) == requests


async def test_close_all_cancels_wave_timers(env: Env) -> None:
    await two_listeners(env)
    await env.room.leave("c1")
    env.room.close_all(CloseReason.RESTART)
    await env.timers.advance(GRACE_MS * 2)
    assert env.status() is WaveStatus.PLAYING
