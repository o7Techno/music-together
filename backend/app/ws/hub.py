"""Реестр WebSocket-соединений. У каждого соединения своя очередь и задача-писатель,
поэтому медленный клиент не тормозит рассылку по комнате."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.core.logging import get_logger
from app.rooms.room import ServerPayload
from app.ws.protocol import (
    WS_CLOSE_FORBIDDEN,
    WS_CLOSE_NOT_FOUND,
    WS_CLOSE_RECONNECT,
    Closed,
    CloseReason,
    ErrorMessage,
    Pong,
)

log = get_logger(__name__)

OUTGOING_LIMIT = 500
_CLOSE_CODES = {
    CloseReason.KICKED: WS_CLOSE_FORBIDDEN,
    CloseReason.DELETED: WS_CLOSE_NOT_FOUND,
    CloseReason.RESTART: WS_CLOSE_RECONNECT,
    CloseReason.REPLACED: WS_CLOSE_RECONNECT,
}

Outgoing = ServerPayload | Pong | ErrorMessage


@dataclass
class _CloseSignal:
    code: int


@dataclass
class Connection:
    conn_id: str
    websocket: WebSocket
    queue: asyncio.Queue[Outgoing | _CloseSignal] = field(
        default_factory=lambda: asyncio.Queue(OUTGOING_LIMIT)
    )
    writer: asyncio.Task[None] | None = None

    def enqueue(self, item: Outgoing | _CloseSignal) -> None:
        try:
            self.queue.put_nowait(item)
        except asyncio.QueueFull:
            # Клиент не читает — отключаем, после переподключения он получит свежий снапшот.
            log.warning("ws_outgoing_overflow", conn_id=self.conn_id)
            self.queue = asyncio.Queue(1)
            self.queue.put_nowait(_CloseSignal(WS_CLOSE_RECONNECT))

    async def run_writer(self) -> None:
        ws = self.websocket
        try:
            while True:
                item = await self.queue.get()
                if isinstance(item, _CloseSignal):
                    if ws.application_state is WebSocketState.CONNECTED:
                        await ws.close(code=item.code)
                    return
                await ws.send_text(item.model_dump_json())
        except Exception:
            log.debug("ws_writer_stopped", conn_id=self.conn_id)


class ConnectionHub:
    def __init__(self) -> None:
        self._connections: dict[str, Connection] = {}

    def register(self, conn_id: str, websocket: WebSocket) -> Connection:
        conn = Connection(conn_id, websocket)
        conn.writer = asyncio.create_task(conn.run_writer())
        self._connections[conn_id] = conn
        return conn

    async def unregister(self, conn_id: str) -> None:
        conn = self._connections.pop(conn_id, None)
        if conn is not None and conn.writer is not None and not conn.writer.done():
            conn.writer.cancel()

    def send(self, conn_id: str, message: Outgoing) -> None:
        conn = self._connections.get(conn_id)
        if conn is not None:
            conn.enqueue(message)

    def close(self, conn_id: str, reason: CloseReason) -> None:
        conn = self._connections.get(conn_id)
        if conn is not None:
            conn.enqueue(Closed(reason=reason))
            conn.enqueue(_CloseSignal(_CLOSE_CODES[reason]))

    def __len__(self) -> int:
        return len(self._connections)
