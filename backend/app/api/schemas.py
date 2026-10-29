"""Схемы REST API."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.core.schema import ApiModel
from app.db.models import User


class Me(ApiModel):
    id: str
    login: str
    display_name: str
    avatar_url: str | None
    has_plus: bool
    provider: str
    provider_connected: bool
    """Токен Яндекса на месте (dev-пользователи — всегда). False → нужен повторный вход."""

    @classmethod
    def of(cls, user: User) -> Me:
        return cls(
            id=user.id,
            login=user.login,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
            has_plus=user.has_plus,
            provider=user.provider,
            provider_connected=user.provider != "yandex" or user.token_enc is not None,
        )


class SessionInfo(ApiModel):
    me: Me | None


class AuthConfig(ApiModel):
    dev_login: bool
    yandex_login: bool


class DevLoginRequest(ApiModel):
    name: str = Field(min_length=1, max_length=40)


class CreateRoomRequest(ApiModel):
    name: str | None = Field(default=None, max_length=80)


class RenameRoomRequest(ApiModel):
    name: str = Field(min_length=1, max_length=80)


class RoomSummary(ApiModel):
    slug: str
    name: str
    is_owner: bool
    last_joined_at: datetime | None = None
    online: int = 0


class RoomDetails(ApiModel):
    id: str
    slug: str
    name: str
    owner_id: str
    is_owner: bool


class SlugResponse(ApiModel):
    slug: str
