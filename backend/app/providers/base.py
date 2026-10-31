"""Абстракция музыкального провайдера (SPEC §7.3).

Вся работа с конкретным сервисом (Яндекс Музыка, фейк) живёт за этим интерфейсом. Провайдер
создаётся на конкретного пользователя: все запросы — его токеном.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, Protocol

from app.core.errors import AppError
from app.core.schema import ApiModel

if TYPE_CHECKING:
    from app.providers.yandex_links import ParsedLink


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
    editable: bool = False
    """Пользователь может менять этот плейлист (он его владелец)."""
    external_url: str | None = None
    """Ссылка на плейлист в самом сервисе, если она есть."""


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


class WaveBatch(ApiModel):
    """Порция треков волны. `session_id` и `batch_id` остаются на сервере и клиентам не уходят."""

    session_id: str
    batch_id: str | None = None
    tracks: list[Track]


class WaveFeedbackKind(StrEnum):
    RADIO_STARTED = "radioStarted"
    TRACK_STARTED = "trackStarted"
    TRACK_FINISHED = "trackFinished"
    SKIP = "skip"
    LIKE = "like"
    UNLIKE = "unlike"
    DISLIKE = "dislike"


class WaveFeedback(ApiModel):
    kind: WaveFeedbackKind
    at_ms: int
    track_id: str | None = None
    played_s: float | None = None
    batch_id: str | None = None


class WaveOption(ApiModel):
    seed: str
    label: str
    default: bool = False


class WaveOptionGroup(ApiModel):
    key: str
    options: list[WaveOption]


class WaveStation(ApiModel):
    kind: str
    id: str
    title: str


class WaveOptions(ApiModel):
    """Что можно выбрать в панели волны: настройки и станции для запуска по зерну."""

    settings: list[WaveOptionGroup] = []
    stations: list[WaveStation] = []


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


class WaveSessionLostError(ProviderError):
    """Сессия волны больше не существует: нужно создать новую."""

    code = "wave_session_lost"
    default_message = "Сессия волны завершилась."


class DuplicateTrackError(ProviderError):
    code = "duplicate"
    status_code = 409
    default_message = "Этот трек уже есть в плейлисте."


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

    async def resolve(self, link: ParsedLink) -> TrackList: ...

    async def start_wave(
        self, seeds: list[str], recent_ids: list[str], *, incognito: bool
    ) -> WaveBatch: ...

    async def next_wave_tracks(self, session_id: str, recent_ids: list[str]) -> WaveBatch: ...

    async def send_wave_feedback(self, session_id: str, events: list[WaveFeedback]) -> None: ...

    async def get_wave_options(self) -> WaveOptions: ...

    async def get_liked_track_ids(self) -> set[str]: ...

    async def like_track(self, track_id: str) -> None: ...

    async def unlike_track(self, track_id: str) -> None: ...

    async def dislike_track(self, track_id: str) -> None: ...

    async def create_playlist(self, title: str) -> PlaylistSummary: ...

    async def add_to_playlist(
        self, ref: str, track_ids: list[str], *, allow_duplicate: bool
    ) -> PlaylistSummary: ...

    async def remove_from_playlist(self, ref: str, track_id: str) -> PlaylistSummary: ...
