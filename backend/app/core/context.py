"""Контейнер зависимостей приложения: один на процесс, хранится в `app.state.ctx`."""

from __future__ import annotations

from dataclasses import dataclass

from app.auth.crypto import TokenCipher
from app.core.clock import Clock
from app.core.config import Settings
from app.core.ratelimit import RateLimiter
from app.db.session import Database
from app.providers.factory import ProviderFactory
from app.rooms.manager import RoomManager
from app.ws.hub import ConnectionHub


@dataclass
class AppContext:
    settings: Settings
    db: Database
    clock: Clock
    hub: ConnectionHub
    rooms: RoomManager
    providers: ProviderFactory
    cipher: TokenCipher | None
    search_limiter: RateLimiter
    stream_limiter: RateLimiter
