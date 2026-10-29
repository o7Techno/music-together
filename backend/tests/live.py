"""Живой сервер для интеграционных тестов: uvicorn в фоновом потоке + асинхронные клиенты.

Сервер настоящий (lifespan, WebSocket, таймеры asyncio), БД — файл SQLite во временном каталоге,
провайдер — FakeProvider. Рестарт сервера = остановить и поднять новый экземпляр на той же БД.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from sqlalchemy.ext.asyncio import create_async_engine
from websockets.asyncio.client import ClientConnection, connect

from app.core.config import Environment, MusicProviderKind, Settings
from app.db.models import Base
from app.main import create_app

ORIGIN = "http://localhost:5173"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def make_settings(db_path: Path) -> Settings:
    return Settings(
        env=Environment.TEST,
        database_url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
        public_origin=ORIGIN,
        music_provider=MusicProviderKind.FAKE,
        log_level="WARNING",
    )


async def create_schema(db_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


@contextmanager
def live_server(settings: Settings):  # type: ignore[no-untyped-def]  # генератор-контекст
    port = free_port()
    config = uvicorn.Config(
        create_app(settings),
        host="127.0.0.1",
        port=port,
        log_level="warning",
        ws_ping_interval=None,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


class Client:
    """Пользователь: REST-клиент со своей cookie + WebSocket-соединения."""

    def __init__(self, base: str, name: str) -> None:
        self.base = base
        self.name = name
        self.http = httpx.AsyncClient(base_url=base, headers={"Origin": ORIGIN})
        self.cookie = ""
        self.user_id = ""

    async def login(self) -> Client:
        r = await self.http.post("/api/auth/dev-login", json={"name": self.name})
        r.raise_for_status()
        self.cookie = r.cookies["mt_session"]
        self.user_id = r.json()["id"]
        return self

    async def create_room(self, name: str | None = None) -> str:
        r = await self.http.post("/api/rooms", json={"name": name})
        r.raise_for_status()
        slug: str = r.json()["slug"]
        return slug

    async def ws(self, slug: str, *, origin: str = ORIGIN, cookie: bool = True) -> Socket:
        headers = {"Origin": origin}
        if cookie:
            headers["Cookie"] = f"mt_session={self.cookie}"
        url = self.base.replace("http", "ws") + f"/ws/rooms/{slug}"
        conn = await connect(url, additional_headers=headers)
        return Socket(conn)

    async def close(self) -> None:
        await self.http.aclose()


class Socket:
    def __init__(self, conn: ClientConnection) -> None:
        self.conn = conn
        self.inbox: list[dict[str, Any]] = []
        """Все полученные сообщения (для проверок постфактум)."""
        self._pending: list[dict[str, Any]] = []
        self._n = 0

    async def send(self, msg: dict[str, Any]) -> str:
        self._n += 1
        msg_id = f"m{self._n}"
        if msg["type"].startswith(("cmd.", "queue.", "chat.")):
            msg = {"clientMsgId": msg_id, **msg}
        await self.conn.send(json.dumps(msg))
        return msg_id

    async def recv(self, timeout: float = 5) -> dict[str, Any]:
        raw = await asyncio.wait_for(self.conn.recv(), timeout)
        msg: dict[str, Any] = json.loads(raw)
        self.inbox.append(msg)
        return msg

    async def next(self, timeout: float = 5) -> dict[str, Any]:
        """Следующее ещё не разобранное сообщение."""
        if self._pending:
            return self._pending.pop(0)
        return await self.recv(timeout)

    async def wait_for(
        self,
        type_: str,
        predicate: Callable[[dict[str, Any]], bool] = lambda _m: True,
        timeout: float = 5,
    ) -> dict[str, Any]:
        """Дождаться сообщения; не подошедшие остаются в буфере для следующих ожиданий."""
        for i, msg in enumerate(self._pending):
            if msg["type"] == type_ and predicate(msg):
                return self._pending.pop(i)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"no {type_} message")
            msg = await self.recv(remaining)
            if msg["type"] == type_ and predicate(msg):
                return msg
            self._pending.append(msg)

    async def unlock(self) -> None:
        await self.send({"type": "client_status", "audioUnlocked": True})

    async def close(self) -> None:
        await self.conn.close()
