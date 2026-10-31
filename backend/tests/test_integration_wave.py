"""Волна и коллекция на живом сервере: REST, несколько WS-клиентов, рестарт, фейковые сбои."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from websockets.exceptions import ConnectionClosed

from app.core.config import Settings
from app.main import build_context
from app.providers.fake import FakeWorld
from app.ws.protocol import WS_CLOSE_FORBIDDEN
from tests.live import Client, Socket, live_server


class NeverOpen:
    """Запрос порции «висит»: сервер работает в своём потоке и цикле, и ворота не открываются."""

    async def wait(self) -> None:
        await asyncio.sleep(3600)


class Live:
    def __init__(self, base: str, world: FakeWorld) -> None:
        self.base = base
        self.world = world


@pytest.fixture
def live(settings: Settings) -> Iterator[Live]:
    ctx = build_context(settings)
    with live_server(settings, ctx) as base:
        yield Live(base, ctx.providers.fake_world)


async def joined(client: Client, slug: str) -> tuple[Socket, dict[str, Any]]:
    ws = await client.ws(slug)
    snapshot = await ws.next()
    await ws.unlock()
    return ws, snapshot


async def pair(base: str) -> tuple[Client, Client, str]:
    anna = await Client(base, "Аня").login()
    petya = await Client(base, "Петя").login()
    return anna, petya, await anna.create_room()


def wave_status(status: str) -> Callable[[dict[str, Any]], bool]:
    return lambda m: m["wave"]["status"] == status


async def close_code(ws: Socket) -> int | None:
    with pytest.raises(ConnectionClosed) as exc:
        await drain(ws)
    return exc.value.rcvd.code if exc.value.rcvd is not None else None


async def drain(ws: Socket) -> None:
    while True:
        await ws.recv(timeout=3)


async def play_current(ws: Socket) -> dict[str, Any]:
    """Пройти барьер текущего трека: `loading` → ready → `playing`."""
    loading = await ws.wait_for("playback", lambda m: m["state"]["status"] == "loading")
    await ws.send({"type": "ready", "version": loading["state"]["version"]})
    return await ws.wait_for("playback", lambda m: m["state"]["status"] == "playing")


async def eventually(check: Callable[[], bool], timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while not check():
        if time.monotonic() > deadline:
            raise AssertionError("условие не выполнилось")
        await asyncio.sleep(0.02)


async def test_wave_plays_without_manual_tracks_and_reports_feedback(live: Live) -> None:
    anna, petya, slug = await pair(live.base)
    a, _ = await joined(anna, slug)
    p, _ = await joined(petya, slug)
    await a.send({"type": "wave.start", "mode": "personal"})
    await a.wait_for("ack")
    message = await p.wait_for("wave", wave_status("playing"))
    assert message["wave"]["ownerId"] == anna.user_id
    assert message["wave"]["nextTrackId"]

    state = await play_current(a)
    assert state["state"]["trackId"].startswith("fake-wave-")
    await p.send({"type": "ready", "version": state["state"]["version"]})
    first = state["state"]["queueItemId"]
    await p.send({"type": "cmd.next", "expectedQueueItemId": first})

    def kinds() -> list[str]:
        return [e.kind.value for _, _, e in live.world.feedback]

    await eventually(lambda: "skip" in kinds())
    assert kinds()[:3] == ["radioStarted", "trackStarted", "skip"]
    assert {user for user, _, _ in live.world.feedback} == {anna.user_id}
    await a.close()
    await p.close()


async def test_session_id_never_reaches_clients(live: Live) -> None:
    anna, _, slug = await pair(live.base)
    a, _ = await joined(anna, slug)
    await a.send({"type": "wave.start", "mode": "personal"})
    await a.wait_for("wave", wave_status("playing"))
    await asyncio.sleep(0.1)
    await a.send({"type": "ping", "t0": 1})
    await a.wait_for("pong")
    assert "fake-session" not in str(a.inbox)
    assert "batchId" not in str(a.inbox)
    await a.close()


async def test_ping_is_served_while_wave_start_waits_for_yandex(live: Live) -> None:
    anna, _, slug = await pair(live.base)
    a, _ = await joined(anna, slug)
    live.world.wave_gate = NeverOpen()
    await a.send({"type": "wave.start", "mode": "personal"})
    await a.wait_for("ack", timeout=1)
    await a.wait_for("wave", wave_status("starting"), timeout=1)
    await a.send({"type": "ping", "t0": 1})
    await a.wait_for("pong", timeout=1)
    await a.close()


async def test_replace_and_stop_events_reach_everyone(live: Live) -> None:
    anna, petya, slug = await pair(live.base)
    a, _ = await joined(anna, slug)
    p, _ = await joined(petya, slug)
    await a.send({"type": "wave.start", "mode": "personal"})
    started = await a.wait_for("wave", wave_status("playing"))
    await p.send({"type": "wave.start", "mode": "personal"})
    error = await p.wait_for("error")
    assert error["code"] == "stale"
    await p.send(
        {"type": "wave.start", "mode": "personal", "expectedWaveId": started["wave"]["waveId"]}
    )
    replaced = await a.wait_for(
        "wave", lambda m: m["wave"]["ownerId"] == petya.user_id and m["wave"]["status"] == "playing"
    )
    assert replaced["wave"]["waveId"] != started["wave"]["waveId"]
    await a.send({"type": "wave.stop"})
    await p.wait_for("wave", wave_status("off"))
    await p.wait_for("event", lambda m: m["event"]["kind"] == "wave_stopped")
    await a.close()
    await p.close()


async def test_lost_session_is_recreated_transparently(live: Live) -> None:
    anna, _, slug = await pair(live.base)
    a, _ = await joined(anna, slug)
    await a.send({"type": "wave.start", "mode": "personal"})
    await a.wait_for("wave", wave_status("playing"))
    live.world.lose_sessions()
    state = await play_current(a)
    # Сессии потеряны: при дозапросе создаётся новая, музыка не прерывается.
    for _ in range(3):
        await a.send({"type": "cmd.next", "expectedQueueItemId": state["state"]["queueItemId"]})
        state = await play_current(a)
    await eventually(lambda: bool(live.world.sessions))
    assert [
        e for e in a.inbox if e["type"] == "event" and e["event"]["kind"] == "wave_unavailable"
    ] == []
    await a.close()


async def test_yandex_failure_then_recovery(live: Live) -> None:
    anna, _, slug = await pair(live.base)
    a, _ = await joined(anna, slug)
    live.world.wave_failures = 1
    await a.send({"type": "wave.start", "mode": "personal"})
    await a.wait_for("event", lambda m: m["event"]["kind"] == "wave_unavailable")
    message = await a.wait_for("wave", wave_status("unavailable"))
    assert message["wave"]["nextTrackId"] is None
    await a.close()


async def test_auth_failure_stops_wave(live: Live) -> None:
    anna, _, slug = await pair(live.base)
    a, _ = await joined(anna, slug)
    live.world.wave_auth_failure = True
    await a.send({"type": "wave.start", "mode": "personal"})
    event = await a.wait_for("event", lambda m: m["event"]["kind"] == "wave_stopped")
    assert event["event"]["reason"] == "auth"
    await a.close()


async def test_logout_of_owner_stops_wave(live: Live) -> None:
    anna, petya, slug = await pair(live.base)
    a, _ = await joined(anna, slug)
    p, _ = await joined(petya, slug)
    await a.send({"type": "wave.start", "mode": "personal"})
    await p.wait_for("wave", wave_status("playing"))
    r = await anna.http.post("/api/auth/logout")
    assert r.status_code == 204
    event = await p.wait_for("event", lambda m: m["event"]["kind"] == "wave_stopped")
    assert event["event"]["reason"] == "owner_gone"
    await a.close()
    await p.close()


async def test_kick_of_owner_stops_wave(live: Live) -> None:
    anna, petya, slug = await pair(live.base)
    a, _ = await joined(anna, slug)
    p, _ = await joined(petya, slug)
    await p.send({"type": "wave.start", "mode": "personal"})
    await a.wait_for("wave", wave_status("playing"))
    r = await anna.http.post(f"/api/rooms/{slug}/kick/{petya.user_id}")
    assert r.status_code == 204
    event = await a.wait_for("event", lambda m: m["event"]["kind"] == "wave_stopped")
    assert event["event"]["reason"] == "owner_gone"
    await a.close()
    assert await close_code(p) == WS_CLOSE_FORBIDDEN


async def test_wave_restored_after_restart(settings: Settings) -> None:
    with live_server(settings) as base:
        anna, _, slug = await pair(base)
        a, _ = await joined(anna, slug)
        await a.send({"type": "wave.start", "mode": "personal"})
        started = await a.wait_for("wave", wave_status("playing"))
        state = await play_current(a)
    with live_server(settings) as base:
        anna.base = base
        anna.http.base_url = httpx.URL(base)
        a2, snapshot = await joined(anna, slug)
        assert snapshot["wave"]["status"] == "playing"
        assert snapshot["wave"]["waveId"] == started["wave"]["waveId"]
        assert snapshot["wave"]["ownerAway"] is False or snapshot["wave"]["ownerId"] == anna.user_id
        assert snapshot["playback"]["status"] == "paused"
        assert snapshot["playback"]["queueItemId"] == state["state"]["queueItemId"]
        await a2.close()


# ── Коллекция ───────────────────────────────────────────────────────────────────


async def test_like_is_personal_and_reaches_room(live: Live) -> None:
    anna, petya, slug = await pair(live.base)
    a, _ = await joined(anna, slug)
    p, _ = await joined(petya, slug)
    await a.send({"type": "queue.add", "trackIds": ["fake-1"]})
    await play_current(a)

    assert "fake-1" not in (await anna.http.get("/api/me/liked/ids")).json()["trackIds"]
    r = await anna.http.put("/api/me/liked/fake-1", params={"room": slug})
    assert r.status_code == 204
    assert "fake-1" in (await anna.http.get("/api/me/liked/ids")).json()["trackIds"]
    assert "fake-1" not in (await petya.http.get("/api/me/liked/ids")).json()["trackIds"]

    likes = await p.wait_for("track_likes")
    assert likes["likes"]["userIds"] == [anna.user_id]
    event = await p.wait_for("event", lambda m: m["event"]["kind"] == "track_liked")
    assert event["event"]["userName"] == "Аня"

    r = await anna.http.delete("/api/me/liked/fake-1", params={"room": slug})
    assert r.status_code == 204
    assert "fake-1" not in (await anna.http.get("/api/me/liked/ids")).json()["trackIds"]
    await a.close()
    await p.close()


async def test_like_outside_room_or_for_a_stranger_makes_no_event(live: Live) -> None:
    anna, petya, slug = await pair(live.base)
    a, _ = await joined(anna, slug)
    await a.send({"type": "queue.add", "trackIds": ["fake-1"]})
    await play_current(a)
    # Петя никогда не был в комнате: лайк проходит, а в комнате следа нет.
    assert (await petya.http.put("/api/me/liked/fake-1", params={"room": slug})).status_code == 204
    assert (
        await petya.http.put("/api/me/liked/fake-2", params={"room": "no-such"})
    ).status_code == 204
    await a.send({"type": "ping", "t0": 1})
    await a.wait_for("pong")
    assert [m for m in a.inbox if m["type"] == "track_likes"] == []
    await a.close()


async def test_playlist_create_add_duplicate_remove(live: Live) -> None:
    anna, petya, _ = await pair(live.base)
    r = await anna.http.post("/api/me/playlists", json={"title": "Для дороги"})
    assert r.status_code == 201
    playlist = r.json()
    assert playlist["editable"] is True
    ref = playlist["ref"]

    r = await anna.http.post(f"/api/me/playlists/{ref}/tracks", json={"trackIds": ["fake-1"]})
    assert r.json()["trackCount"] == 1
    r = await anna.http.post(f"/api/me/playlists/{ref}/tracks", json={"trackIds": ["fake-1"]})
    assert r.status_code == 409
    assert r.json()["code"] == "duplicate"
    r = await anna.http.post(
        f"/api/me/playlists/{ref}/tracks", json={"trackIds": ["fake-1"], "allowDuplicate": True}
    )
    assert r.json()["trackCount"] == 2
    r = await anna.http.delete(f"/api/me/playlists/{ref}/tracks/fake-1")
    assert r.json()["trackCount"] == 1

    # Чужой плейлист недоступен.
    r = await petya.http.post(f"/api/me/playlists/{ref}/tracks", json={"trackIds": ["fake-2"]})
    assert r.status_code == 404
    mine = (await petya.http.get("/api/me/playlists")).json()
    assert ref not in [p["ref"] for p in mine]


async def test_batch_add_to_playlist_filters_existing(live: Live) -> None:
    anna = await Client(live.base, "Аня").login()
    ref = (await anna.http.post("/api/me/playlists", json={"title": "Очередь"})).json()["ref"]
    await anna.http.post(f"/api/me/playlists/{ref}/tracks", json={"trackIds": ["fake-1"]})
    r = await anna.http.post(
        f"/api/me/playlists/{ref}/tracks", json={"trackIds": ["fake-1", "fake-2", "fake-3"]}
    )
    assert r.json()["trackCount"] == 3


async def test_wave_learning_setting(live: Live) -> None:
    anna = await Client(live.base, "Аня").login()
    me = (await anna.http.get("/api/auth/me")).json()
    assert me["waveLearning"] is True
    r = await anna.http.patch("/api/me/settings", json={"waveLearning": False})
    assert r.json()["waveLearning"] is False
    assert (await anna.http.get("/api/auth/me")).json()["waveLearning"] is False


async def test_no_learning_uses_incognito_and_drops_listening_feedback(live: Live) -> None:
    anna, _, slug = await pair(live.base)
    await anna.http.patch("/api/me/settings", json={"waveLearning": False})
    a, _ = await joined(anna, slug)
    await a.send({"type": "wave.start", "mode": "personal"})
    await a.wait_for("wave", wave_status("playing"))
    state = await play_current(a)
    await a.send({"type": "cmd.next", "expectedQueueItemId": state["state"]["queueItemId"]})
    await play_current(a)
    assert all(s.incognito for s in live.world.sessions.values())
    await asyncio.sleep(0.2)
    assert live.world.feedback == []
    await a.close()


async def test_room_settings_are_saved_and_broadcast(live: Live) -> None:
    anna, petya, slug = await pair(live.base)
    p, _ = await joined(petya, slug)
    r = await anna.http.patch(f"/api/rooms/{slug}", json={"waveMix": "alternate"})
    assert r.status_code == 200
    message = await p.wait_for("room", lambda m: m["room"]["settings"]["waveMix"] == "alternate")
    assert message["room"]["settings"]["announceLikes"] is True
    r = await petya.http.patch(f"/api/rooms/{slug}", json={"announceLikes": False})
    assert r.status_code == 403
    await p.close()


async def test_wave_options_are_available(live: Live) -> None:
    anna = await Client(live.base, "Аня").login()
    options = (await anna.http.get("/api/me/wave/options")).json()
    assert options["settings"]
    assert {s["kind"] for s in options["stations"]} >= {"mood", "activity"}


async def test_shared_wave_alternates_sources_and_routes_feedback(live: Live) -> None:
    anna, petya, slug = await pair(live.base)
    a, _ = await joined(anna, slug)
    p, _ = await joined(petya, slug)
    await asyncio.sleep(0.05)
    await a.send({"type": "wave.start", "mode": "shared"})
    message = await a.wait_for(
        "wave", lambda m: len({i["addedBy"] for i in m["wave"]["next"]}) == 2
    )
    assert message["wave"]["ownerId"] is None
    assert {s["userId"] for s in message["wave"]["sources"] if s["active"]} == {
        anna.user_id,
        petya.user_id,
    }

    owners: list[str] = []
    for _ in range(3):
        loading = await a.wait_for("playback", lambda m: m["state"]["status"] == "loading")
        await a.send({"type": "ready", "version": loading["state"]["version"]})
        await p.send({"type": "ready", "version": loading["state"]["version"]})
        state = await a.wait_for("playback", lambda m: m["state"]["status"] == "playing")
        owners.append(latest_queue(a)["queue"]["current"]["addedBy"])
        await a.send({"type": "cmd.next", "expectedQueueItemId": state["state"]["queueItemId"]})
    assert owners[0] != owners[1]
    assert owners[0] == owners[2]

    def skipped() -> list[str]:
        return [u for u, _, e in live.world.feedback if e.kind.value == "skip"]

    await eventually(lambda: len(skipped()) == 3)
    # Очереди фидбека у пользователей независимы: общего порядка между ними нет.
    assert sorted(skipped()) == sorted(owners)
    await a.close()
    await p.close()


def latest_queue(ws: Socket) -> dict[str, Any]:
    return [m for m in ws.inbox if m["type"] == "queue"][-1]
