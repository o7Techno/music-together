"""Общие фабрики и тестовые дублёры."""

from __future__ import annotations

from collections import defaultdict

from app.providers.base import ArtistRef, Track
from app.rooms.queue import QueueItem, make_item
from app.rooms.room import ServerPayload
from app.ws.protocol import CloseReason


def track(n: int | str, duration_ms: int = 60_000) -> Track:
    return Track(
        id=f"t{n}",
        title=f"Track {n}",
        artists=[ArtistRef(id="a", name="Artist")],
        duration_ms=duration_ms,
    )


def item(n: int | str, duration_ms: int = 60_000) -> QueueItem:
    return make_item(track(n, duration_ms), "u1", 0)


class RecordingOutbox:
    def __init__(self) -> None:
        self.sent: dict[str, list[ServerPayload]] = defaultdict(list)
        self.closed: dict[str, CloseReason] = {}

    def send(self, conn_id: str, message: ServerPayload) -> None:
        self.sent[conn_id].append(message)

    def close(self, conn_id: str, reason: CloseReason) -> None:
        self.closed[conn_id] = reason

    def of_type(self, conn_id: str, type_: str) -> list[ServerPayload]:
        return [m for m in self.sent[conn_id] if m.type == type_]

    def clear(self) -> None:
        self.sent.clear()
