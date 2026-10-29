"""Абстракция музыкального провайдера (SPEC §7.3).

Вся работа с конкретным сервисом (Яндекс Музыка, фейк) живёт за этим интерфейсом. Провайдер
создаётся на конкретного пользователя: все запросы — его токеном.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol

from app.core.errors import AppError
from app.core.schema import ApiModel


class ArtistRef(ApiModel):
    id: str
    name: str


class Track(ApiModel):
    id: str
    title: str
    artists: list[ArtistRef]
    album_id: str | None = None
    album_title: str | None = None
    duration_ms: int
    cover_url: str | None = None
    """Шаблон обложки с `{size}` вместо размера, например `https://…/{size}` → `400x400`."""
    available: bool = True


class AlbumSummary(ApiModel):
    id: str
    title: str
    artists: list[ArtistRef]
    year: int | None = None
    track_count: int | None = None
    cover_url: str | None = None


class ArtistSummary(ApiModel):
    id: str
    name: str
    cover_url: str | None = None


class PlaylistSummary(ApiModel):
    ref: str
    """Ссылка на плейлист внутри провайдера: `owner:kind` или UUID."""
    title: str
    owner_name: str | None = None
    track_count: int | None = None
    cover_url: str | None = None


class EntityKind(StrEnum):
    TRACK = "track"
    ALBUM = "album"
    ARTIST = "artist"
    PLAYLIST = "playlist"


class BestResult(ApiModel):
    kind: EntityKind
    track: Track | None = None
    album: AlbumSummary | None = None
    artist: ArtistSummary | None = None
    playlist: PlaylistSummary | None = None


class SearchResult(ApiModel):
    best: BestResult | None = None
    tracks: list[Track] = []
    albums: list[AlbumSummary] = []
    artists: list[ArtistSummary] = []
    playlists: list[PlaylistSummary] = []


class TrackList(ApiModel):
    """Набор треков сущности (альбом, плейлист, артист, «Мне нравится»)."""

    kind: EntityKind | Literal["liked"]
    id: str
    title: str
    subtitle: str | None = None
    cover_url: str | None = None
    tracks: list[Track]
    albums: list[AlbumSummary] = []
    """Для артиста — его альбомы."""


class ResolvedEntity(ApiModel):
    kind: EntityKind
    id: str


class StreamMode(StrEnum):
    DIRECT = "direct"
    PROXY = "proxy"


class StreamInfo(ApiModel):
    track_id: str
    mode: StreamMode
    url: str
    mirrors: list[str] = []
    codec: str
    bitrate: int
    expires_at: datetime | None = None


class UserProfile(ApiModel):
    external_id: str
    login: str
    display_name: str
    avatar_url: str | None = None
    has_plus: bool


# ── Ошибки провайдера: переводятся в понятные пользователю сообщения ─────────────


class ProviderError(AppError):
    code = "provider_error"
    status_code = 502
    default_message = "Сервис музыки временно недоступен. Попробуйте позже."


class TrackUnavailableError(ProviderError):
    code = "track_unavailable"
    status_code = 422
    default_message = "Трек недоступен в вашем регионе или для вашего аккаунта."


class SubscriptionRequiredError(ProviderError):
    code = "subscription_required"
    status_code = 402
    default_message = "Для прослушивания нужна подписка Плюс."


class ProviderAuthError(ProviderError):
    code = "provider_auth"
    status_code = 401
    default_message = "Вход в Яндекс Музыку устарел — войдите заново."


class ProviderNotFoundError(ProviderError):
    code = "provider_not_found"
    status_code = 404
    default_message = "Не нашли такой трек, альбом или плейлист."


class MusicProvider(Protocol):
    async def search(self, query: str) -> SearchResult: ...

    async def get_tracks(self, track_ids: list[str]) -> list[Track]: ...

    async def get_album(self, album_id: str) -> TrackList: ...

    async def get_playlist(self, ref: str) -> TrackList: ...

    async def get_artist(self, artist_id: str) -> TrackList: ...

    async def get_user_playlists(self) -> list[PlaylistSummary]: ...

    async def get_liked_tracks(self) -> TrackList: ...

    async def get_liked_albums(self) -> list[AlbumSummary]: ...

    async def get_stream(self, track_id: str) -> StreamInfo: ...
