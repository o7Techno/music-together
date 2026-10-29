"""Интеграционные тесты: несколько WS-клиентов в комнате на FakeProvider (SPEC §10)."""

from __future__ import annotations

import httpx
import pytest
from websockets.exceptions import ConnectionClosed

from app.core.config import Settings
from app.ws.protocol import WS_CLOSE_FORBIDDEN, WS_CLOSE_NOT_FOUND, WS_CLOSE_UNAUTHORIZED
from tests.live import Client, Socket, live_server


async def two_users(base: str) -> tuple[Client, Client, str]:
    anna = await Client(base, "Аня").login()
    petya = await Client(base, "Петя").login()
    slug = await anna.create_room()
    return anna, petya, slug


async def joined(client: Client, slug: str) -> tuple[Socket, dict]:  # type: ignore[type-arg]
    ws = await client.ws(slug)
    snapshot = await ws.next()
    assert snapshot["type"] == "snapshot"
    await ws.unlock()
    return ws, snapshot


async def test_snapshot_is_first_message(server: str) -> None:
    anna, _, slug = await two_users(server)
    ws, snapshot = await joined(anna, slug)
    assert snapshot["selfUserId"] == anna.user_id
    assert snapshot["room"]["slug"] == slug
    assert snapshot["playback"]["status"] == "paused"
    assert snapshot["queue"]["upcoming"] == []
    await ws.close()


@pytest.mark.parametrize(
    ("origin", "cookie", "code"),
    [
        ("http://evil.example", True, WS_CLOSE_FORBIDDEN),
        ("http://localhost:5173", False, WS_CLOSE_UNAUTHORIZED),
    ],
)
async def test_ws_rejects_bad_origin_and_anonymous(
    server: str, origin: str, cookie: bool, code: int
) -> None:
    anna, _, slug = await two_users(server)
    ws = await anna.ws(slug, origin=origin, cookie=cookie)
    with pytest.raises(ConnectionClosed) as exc:
        await ws.recv()
    assert exc.value.rcvd is not None
    assert exc.value.rcvd.code == code


async def test_ws_unknown_room(server: str) -> None:
    anna, _, _ = await two_users(server)
    ws = await anna.ws("nope-nope")
    with pytest.raises(ConnectionClosed) as exc:
        await ws.recv()
    assert exc.value.rcvd is not None
    assert exc.value.rcvd.code == WS_CLOSE_NOT_FOUND


async def test_add_track_barrier_and_start_for_two_clients(server: str) -> None:
    anna, petya, slug = await two_users(server)
    a, _ = await joined(anna, slug)
    p, _ = await joined(petya, slug)

    msg_id = await a.send({"type": "queue.add", "trackIds": ["fake-3", "fake-4"]})
    await a.wait_for("ack", lambda m: m["clientMsgId"] == msg_id)
    loading = await p.wait_for("playback", lambda m: m["state"]["status"] == "loading")
    assert loading["state"]["trackId"] == "fake-3"
    version = loading["state"]["version"]

    await a.send({"type": "ready", "version": version})
    await p.send({"type": "ready", "version": version})
    playing_a = await a.wait_for("playback", lambda m: m["state"]["status"] == "playing")
    playing_p = await p.wait_for("playback", lambda m: m["state"]["status"] == "playing")
    assert playing_a["state"] == playing_p["state"]
    # Старт назначен в будущем.
    pong_a = await ping(a)
    assert playing_a["state"]["anchorServerMs"] > pong_a["serverTime"] - 1000


async def close_code(ws: Socket) -> int | None:
    try:
        while True:
            await ws.recv(timeout=5)
    except ConnectionClosed as exc:
        return exc.rcvd.code if exc.rcvd else None


async def ping(ws: Socket) -> dict:  # type: ignore[type-arg]
    await ws.send({"type": "ping", "t0": 1.0})
    return await ws.wait_for("pong")


async def test_pong_echoes_t0_with_server_time(server: str) -> None:
    anna, _, slug = await two_users(server)
    a, snapshot = await joined(anna, slug)
    await a.send({"type": "ping", "t0": 123.5})
    pong = await a.wait_for("pong")
    assert pong["t0"] == 123.5
    assert abs(pong["serverTime"] - snapshot["serverTime"]) < 5000


async def test_double_next_only_one_skip(server: str) -> None:
    anna, petya, slug = await two_users(server)
    a, _ = await joined(anna, slug)
    p, _ = await joined(petya, slug)
    await a.send({"type": "queue.add", "trackIds": ["fake-1", "fake-2", "fake-3"]})
    loading = await p.wait_for("playback", lambda m: m["state"]["trackId"] == "fake-1")
    current = loading["state"]["queueItemId"]

    id_a = await a.send({"type": "cmd.next", "expectedQueueItemId": current})
    id_p = await p.send({"type": "cmd.next", "expectedQueueItemId": current})
    await a.wait_for("ack", lambda m: m["clientMsgId"] == id_a)
    err = await p.wait_for("error", lambda m: m["clientMsgId"] == id_p)
    assert err["code"] == "stale"
    queue = (await a.wait_for("queue", lambda m: m["queue"]["current"]["track"]["id"] == "fake-2"))[
        "queue"
    ]
    assert [i["track"]["id"] for i in queue["upcoming"]] == ["fake-3"]


async def test_unavailable_track_is_rejected_on_add(server: str) -> None:
    anna, _, slug = await two_users(server)
    a, _ = await joined(anna, slug)
    msg_id = await a.send({"type": "queue.add", "trackIds": ["fake-unavailable"]})
    err = await a.wait_for("error", lambda m: m["clientMsgId"] == msg_id)
    assert err["code"] == "track_unavailable"


async def test_invalid_message_gets_error(server: str) -> None:
    anna, _, slug = await two_users(server)
    a, _ = await joined(anna, slug)
    await a.conn.send('{"type": "cmd.seek", "positionMs": -5}')
    err = await a.wait_for("error")
    assert err["code"] == "bad_message"


async def test_reconnect_gets_fresh_snapshot(server: str) -> None:
    anna, petya, slug = await two_users(server)
    a, _ = await joined(anna, slug)
    p, _ = await joined(petya, slug)
    await a.send({"type": "queue.add", "trackIds": ["fake-5"]})
    await p.wait_for("playback", lambda m: m["state"]["status"] == "loading")
    await p.close()
    # Пока Петя офлайн, очередь меняется.
    await a.send({"type": "queue.add", "trackIds": ["fake-6"]})
    await a.wait_for("queue", lambda m: len(m["queue"]["upcoming"]) == 1)
    p2, snapshot = await joined(petya, slug)
    assert snapshot["queue"]["current"]["track"]["id"] == "fake-5"
    assert [i["track"]["id"] for i in snapshot["queue"]["upcoming"]] == ["fake-6"]
    await p2.close()


async def test_kick_closes_and_bans(server: str) -> None:
    anna, petya, slug = await two_users(server)
    a, _ = await joined(anna, slug)
    p, _ = await joined(petya, slug)
    r = await anna.http.post(f"/api/rooms/{slug}/kick/{petya.user_id}")
    assert r.status_code == 204
    closed = await p.wait_for("closed")
    assert closed["reason"] == "kicked"
    p2 = await petya.ws(slug)
    with pytest.raises(ConnectionClosed) as exc:
        await p2.recv()
    assert exc.value.rcvd is not None
    assert exc.value.rcvd.code == WS_CLOSE_FORBIDDEN
    await a.close()


async def test_room_restored_after_server_restart(settings: Settings) -> None:
    with live_server(settings) as base:
        anna, _, slug = await two_users(base)
        a, _ = await joined(anna, slug)
        await a.send({"type": "queue.add", "trackIds": ["fake-8", "fake-9"]})
        loading = await a.wait_for("playback", lambda m: m["state"]["status"] == "loading")
        await a.send({"type": "ready", "version": loading["state"]["version"]})
        await a.wait_for("playback", lambda m: m["state"]["status"] == "playing")
        # Сервер останавливается при живом соединении (graceful shutdown).
    # uvicorn закрывает WS кодом 1012 (Service Restart): клиент понимает это как «переподключитесь».
    assert await close_code(a) in (1012, 4012)

    with live_server(settings) as base:
        anna.base = base
        anna.http.base_url = httpx.URL(base)
        a2, snapshot = await joined(anna, slug)
        assert snapshot["playback"]["status"] == "paused"
        assert snapshot["playback"]["trackId"] == "fake-8"
        assert [i["track"]["id"] for i in snapshot["queue"]["upcoming"]] == ["fake-9"]
        await a2.close()
