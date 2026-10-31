"""YandexProvider (SPEC §6) — вся работа с библиотекой `yandex-music` только здесь.

Каждый экземпляр работает токеном одного пользователя. Политика запросов:
- таймаут на запрос, ретраи с бэкоффом на сетевые ошибки и 5xx, без ретраев на 4xx;
- ограничение частоты запросов на пользователя;
- TTL-кеш метаданных (публичные сущности — общий, пользовательские — на пользователя);
  ссылки на аудио не кешируются;
- ошибки библиотеки → понятные пользователю (`ProviderError` и наследники).
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from typing import Any, TypeVar

from yandex_music import ClientAsync, SessionEvent, SessionFeedback
from yandex_music.exceptions import (
    BadRequestError,
    NetworkError,
    NotFoundError,
    TimedOutError,
    UnauthorizedError,
    YandexMusicError,
)
from yandex_music.utils.difference import Difference
from yandex_music.utils.request_async import Request

from app.core.logging import get_logger
from app.core.ratelimit import RateLimiter
from app.providers.base import (
    AlbumSummary,
    ArtistRef,
    ArtistSummary,
    BestResult,
    DuplicateTrackError,
    EntityKind,
    PlaylistSummary,
    ProviderAuthError,
    ProviderError,
    ProviderNotFoundError,
    SearchResult,
    StreamInfo,
    StreamMode,
    SubscriptionRequiredError,
    Track,
    TrackList,
    TrackUnavailableError,
    WaveBatch,
    WaveFeedback,
    WaveOption,
    WaveOptionGroup,
    WaveOptions,
    WaveSessionLostError,
    WaveStation,
)
from app.providers.yandex_links import ParsedLink

log = get_logger(__name__)
T = TypeVar("T")

# Незашифрованные форматы, которые браузеры играют напрямую (DECISIONS D-007).
BROWSER_CODECS = ["aac-mp4", "he-aac-mp4", "mp3", "aac", "he-aac"]
REQUEST_TIMEOUT_S = 10
RETRY_DELAYS_S = (0.3, 1.0)
PUBLIC_TTL_S = 15 * 60
USER_TTL_S = 2 * 60
SEARCH_TTL_S = 5 * 60
CACHE_MAX_ENTRIES = 2000
TRACKS_BATCH = 250
LIKED_LIMIT = 2000
PLAYLIST_LIMIT = 5000
WAVE_OPTIONS_TTL_S = 15 * 60
WAVE_QUEUE_LIMIT = 100
WAVE_STATION_KINDS = ("mood", "activity", "genre")
PLAYLIST_CHANGE_ATTEMPTS = 3
PLAYLIST_DIFF_CHUNK = 100
FEEDBACK_FROM = "music-together"
_TS_IN_URL = re.compile(r"[,/]ts=([0-9a-f]{8,})")


class TTLCache:
    """Простой LRU с временем жизни записей (monotonic)."""

    def __init__(self, max_entries: int = CACHE_MAX_ENTRIES) -> None:
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._max = max_entries

    def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if expires < time.monotonic():
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl_s: float) -> None:
        self._data[key] = (time.monotonic() + ttl_s, value)
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


# ── Маппинг моделей библиотеки ──────────────────────────────────────────────────


def _cover(obj: Any) -> str | None:
    uri = getattr(obj, "cover_uri", None) or getattr(obj, "og_image", None)
    if not uri:
        cover = getattr(obj, "cover", None)
        uri = getattr(cover, "uri", None) if cover is not None else None
    if not uri:
        return None
    return "https://" + str(uri).removeprefix("https://").replace("%%", "{size}")


def _artists(raw: Iterable[Any] | None) -> list[ArtistRef]:
    return [ArtistRef(id=str(a.id), name=a.name) for a in raw or [] if a.id is not None and a.name]


def map_track(t: Any) -> Track | None:
    if t is None or t.id is None or not t.title:
        return None
    album = t.albums[0] if t.albums else None
    return Track(
        id=str(t.id),
        title=t.title + (f" ({t.version})" if getattr(t, "version", None) else ""),
        artists=_artists(t.artists),
        album_id=str(album.id) if album is not None and album.id is not None else None,
        album_title=album.title if album is not None else None,
        duration_ms=int(t.duration_ms or 0),
        cover_url=_cover(t),
        available=t.available is not False,
    )


def map_album(a: Any) -> AlbumSummary:
    return AlbumSummary(
        id=str(a.id),
        title=a.title or "Без названия",
        artists=_artists(a.artists),
        year=a.year,
        track_count=a.track_count,
        cover_url=_cover(a),
    )


def map_artist(a: Any) -> ArtistSummary:
    return ArtistSummary(id=str(a.id), name=a.name or "?", cover_url=_cover(a))


def playlist_ref(p: Any) -> str:
    owner = getattr(p, "owner", None)
    if owner is not None and owner.uid is not None and p.kind is not None:
        return f"{owner.uid}:{p.kind}"
    return str(p.playlist_uuid)


def map_playlist(p: Any, uid: str | None = None) -> PlaylistSummary:
    owner = getattr(p, "owner", None)
    owner_uid = str(owner.uid) if owner is not None and owner.uid is not None else None
    url = (
        f"https://music.yandex.ru/users/{owner_uid}/playlists/{p.kind}"
        if owner_uid and p.kind is not None
        else None
    )
    return PlaylistSummary(
        ref=playlist_ref(p),
        title=p.title or "Плейлист",
        owner_name=(owner.name or owner.login) if owner is not None else None,
        track_count=p.track_count,
        cover_url=_cover(p),
        editable=uid is not None and owner_uid == uid,
        external_url=url,
    )


def map_wave_tracks(sequence: Iterable[Any] | None) -> list[Track]:
    """Только настоящие треки, которые можно сыграть (реклама, пустые и без длительности — нет)."""
    tracks: list[Track] = []
    for item in sequence or []:
        if getattr(item, "type", None) != "track":
            continue
        track = map_track(item.track)
        if track is not None and track.available and track.duration_ms > 0:
            tracks.append(track)
    return tracks


def wave_event(event: WaveFeedback) -> SessionFeedback:
    timestamp = datetime.fromtimestamp(event.at_ms / 1000, tz=UTC)
    return SessionFeedback(
        SessionEvent(
            event.kind.value,
            timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            track_id=event.track_id,
            total_played_seconds=event.played_s,
        ),
        event.batch_id,
        FEEDBACK_FROM if event.kind.value == "radioStarted" else None,
    )


def _tracks(raw: Iterable[Any]) -> list[Track]:
    return [t for t in (map_track(x) for x in raw) if t is not None]


def stream_expiry(url: str) -> datetime | None:
    m = _TS_IN_URL.search(url)
    if m is None:
        return None
    try:
        return datetime.fromtimestamp(int(m.group(1), 16), tz=UTC)
    except (ValueError, OverflowError, OSError):
        return None


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def make_client(token: str | None, proxy_url: str | None) -> ClientAsync:
    request = Request(proxy_url=proxy_url or None, timeout=REQUEST_TIMEOUT_S)
    return ClientAsync(token, request=request, report_unknown_fields=False)


# ── Провайдер ───────────────────────────────────────────────────────────────────


TokenRefresher = Callable[[], Awaitable[str | None]]
"""Обновить access_token через refresh_token; None — обновить не удалось."""


class YandexProvider:
    def __init__(
        self,
        *,
        user_key: str,
        uid: str,
        token: str,
        proxy_url: str | None,
        public_cache: TTLCache,
        limiter: RateLimiter,
        refresher: TokenRefresher | None = None,
        client_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.user_key = user_key
        self.uid = uid
        self._proxy = proxy_url
        self._factory = client_factory or (lambda tok: make_client(tok, proxy_url))
        self._client = self._factory(token)
        self._public = public_cache
        self._private = TTLCache(200)
        self._limiter = limiter
        self._refresher = refresher
        self._refreshed = False
        self._playlist_locks: dict[str, asyncio.Lock] = {}

    # ── Политика запросов ───────────────────────────────────────────────────────

    async def _throttle(self) -> None:
        for _ in range(10):
            if self._limiter.allow(self.user_key):
                return
            await asyncio.sleep(0.1)
        raise ProviderError("Слишком много запросов к Яндекс Музыке — подождите пару секунд.")

    async def _call(self, op: Callable[[Any], Awaitable[T]], *, retry: bool = True) -> T:
        """Вызов библиотеки с ретраями на сеть/5xx и переводом ошибок.

        `retry=False` — для неидемпотентных изменений: сетевую ошибку получает вызывающий.
        """
        attempt = 0
        while True:
            await self._throttle()
            try:
                return await op(self._client)
            except UnauthorizedError as e:
                if self._refresher is not None and not self._refreshed:
                    self._refreshed = True
                    token = await self._refresher()
                    if token:
                        self._client = self._factory(token)
                        continue
                raise ProviderAuthError from e
            except NotFoundError as e:
                raise ProviderNotFoundError from e
            except BadRequestError as e:
                raise ProviderNotFoundError from e
            except (TimedOutError, NetworkError) as e:
                if not retry:
                    raise
                if attempt >= len(RETRY_DELAYS_S):
                    log.warning("yandex_unavailable", error=type(e).__name__)
                    raise ProviderError from e
                await asyncio.sleep(RETRY_DELAYS_S[attempt])
                attempt += 1
            except YandexMusicError as e:
                log.warning("yandex_error", error=type(e).__name__)
                raise ProviderError from e

    async def _cached(
        self, cache: TTLCache, key: str, ttl_s: float, load: Callable[[], Awaitable[T]]
    ) -> T:
        hit = cache.get(key)
        if hit is not None:
            return hit  # type: ignore[no-any-return]  # кеш хранит ровно то, что вернул load
        value = await load()
        cache.set(key, value, ttl_s)
        return value

    # ── MusicProvider ───────────────────────────────────────────────────────────

    async def search(self, query: str) -> SearchResult:
        q = query.strip()
        if not q:
            return SearchResult()

        async def load() -> SearchResult:
            sr = await self._call(lambda c: c.search(q))
            return self._map_search(sr)

        return await self._cached(self._public, f"search:{q.lower()}", SEARCH_TTL_S, load)

    @staticmethod
    def _map_search(sr: Any) -> SearchResult:
        if sr is None:
            return SearchResult()
        tracks = _tracks(sr.tracks.results if sr.tracks else [])
        albums = [map_album(a) for a in (sr.albums.results if sr.albums else [])]
        artists = [map_artist(a) for a in (sr.artists.results if sr.artists else [])]
        playlists = [map_playlist(p) for p in (sr.playlists.results if sr.playlists else [])]
        best: BestResult | None = None
        if sr.best is not None and sr.best.result is not None:
            r = sr.best.result
            match sr.best.type:
                case "track":
                    track = map_track(r)
                    best = BestResult(kind=EntityKind.TRACK, track=track) if track else None
                case "album":
                    best = BestResult(kind=EntityKind.ALBUM, album=map_album(r))
                case "artist":
                    best = BestResult(kind=EntityKind.ARTIST, artist=map_artist(r))
                case "playlist":
                    best = BestResult(kind=EntityKind.PLAYLIST, playlist=map_playlist(r))
                case _:
                    best = None
        return SearchResult(
            best=best, tracks=tracks, albums=albums, artists=artists, playlists=playlists
        )

    async def get_tracks(self, track_ids: list[str]) -> list[Track]:
        ids = [i for i in dict.fromkeys(track_ids) if i]
        result: dict[str, Track] = {}
        missing: list[str] = []
        for i in ids:
            hit = self._public.get(f"track:{i}")
            if hit is not None:
                result[i] = hit
            else:
                missing.append(i)
        for chunk in _chunks(missing, TRACKS_BATCH):
            raw = await self._fetch_tracks(chunk)
            for track in _tracks(raw or []):
                result[track.id] = track
                self._public.set(f"track:{track.id}", track, PUBLIC_TTL_S)
        return [result[i] for i in ids if i in result]

    async def _fetch_tracks(self, ids: list[str]) -> list[Any]:
        result: list[Any] = await self._call(lambda c: c.tracks(ids))
        return result

    async def get_album(self, album_id: str) -> TrackList:
        async def load() -> TrackList:
            album = await self._call(lambda c: c.albums_with_tracks(album_id))
            if album is None:
                raise ProviderNotFoundError
            tracks = _tracks(t for volume in album.volumes or [] for t in volume)
            summary = map_album(album)
            return TrackList(
                kind=EntityKind.ALBUM,
                id=str(album.id),
                title=summary.title,
                subtitle=", ".join(a.name for a in summary.artists) or None,
                cover_url=summary.cover_url,
                tracks=tracks,
            )

        return await self._cached(self._public, f"album:{album_id}", PUBLIC_TTL_S, load)

    async def get_playlist(self, ref: str) -> TrackList:
        cache = self._private if ref.startswith(f"{self.uid}:") else self._public
        ttl = USER_TTL_S if cache is self._private else PUBLIC_TTL_S

        async def load() -> TrackList:
            if ":" in ref:
                owner, kind = ref.split(":", 1)
                if not kind.isdigit():
                    raise ProviderNotFoundError
                playlist = await self._call(lambda c: c.users_playlists(int(kind), owner))
            else:
                playlist = await self._call(lambda c: c.playlist(ref))
            if playlist is None:
                raise ProviderNotFoundError
            tracks = await self._resolve_short_tracks(playlist.tracks or [], PLAYLIST_LIMIT)
            summary = map_playlist(playlist)
            return TrackList(
                kind=EntityKind.PLAYLIST,
                id=summary.ref,
                title=summary.title,
                subtitle=summary.owner_name,
                cover_url=summary.cover_url,
                tracks=tracks,
            )

        return await self._cached(cache, f"playlist:{ref}", ttl, load)

    async def _resolve_short_tracks(self, shorts: list[Any], limit: int) -> list[Track]:
        """TrackShort → Track: у части элементов трек уже вложен, остальные догружаем пачками."""
        shorts = shorts[:limit]
        order: list[str] = []
        known: dict[str, Track] = {}
        for s in shorts:
            track = map_track(getattr(s, "track", None))
            tid = track.id if track else str(getattr(s, "id", "") or "").split(":")[0]
            if not tid:
                continue
            order.append(tid)
            if track:
                known[tid] = track
        missing = [t for t in order if t not in known]
        for track in await self.get_tracks(missing):
            known[track.id] = track
        return [known[t] for t in order if t in known]

    async def get_artist(self, artist_id: str) -> TrackList:
        async def load() -> TrackList:
            brief, top, albums = await asyncio.gather(
                self._call(lambda c: c.artists_brief_info(artist_id)),
                self._call(lambda c: c.artists_tracks(artist_id, page_size=50)),
                self._call(lambda c: c.artists_direct_albums(artist_id, page_size=50)),
            )
            if brief is None or brief.artist is None:
                raise ProviderNotFoundError
            tracks = _tracks(top.tracks if top else brief.popular_tracks or [])
            return TrackList(
                kind=EntityKind.ARTIST,
                id=str(brief.artist.id),
                title=brief.artist.name or "Исполнитель",
                cover_url=_cover(brief.artist),
                tracks=tracks,
                albums=[map_album(a) for a in (albums.albums if albums else [])],
            )

        return await self._cached(self._public, f"artist:{artist_id}", PUBLIC_TTL_S, load)

    async def get_user_playlists(self) -> list[PlaylistSummary]:
        async def load() -> list[PlaylistSummary]:
            lists = await self._call(lambda c: c.users_playlists_list(self.uid))
            return [map_playlist(p, self.uid) for p in lists or []]

        return await self._cached(self._private, "my-playlists", USER_TTL_S, load)

    async def get_liked_tracks(self) -> TrackList:
        async def load() -> TrackList:
            likes = await self._call(lambda c: c.users_likes_tracks(self.uid))
            ids = [str(s.track_id).split(":")[0] for s in (likes.tracks if likes else [])]
            tracks = await self.get_tracks(ids[:LIKED_LIMIT])
            return TrackList(kind="liked", id="liked", title="Мне нравится", tracks=tracks)

        return await self._cached(self._private, "liked", USER_TTL_S, load)

    async def get_liked_albums(self) -> list[AlbumSummary]:
        async def load() -> list[AlbumSummary]:
            likes = await self._call(lambda c: c.users_likes_albums(self.uid))
            return [map_album(like.album) for like in likes or [] if like.album is not None]

        return await self._cached(self._private, "liked-albums", USER_TTL_S, load)

    async def resolve(self, parsed: ParsedLink) -> TrackList:
        match parsed.kind:
            case EntityKind.TRACK:
                tracks = await self.get_tracks([parsed.id])
                if not tracks:
                    raise ProviderNotFoundError
                t = tracks[0]
                return TrackList(
                    kind=EntityKind.TRACK,
                    id=t.id,
                    title=t.title,
                    subtitle=", ".join(a.name for a in t.artists),
                    cover_url=t.cover_url,
                    tracks=tracks,
                )
            case EntityKind.ALBUM:
                return await self.get_album(parsed.id)
            case EntityKind.PLAYLIST:
                return await self.get_playlist(parsed.id)
            case EntityKind.ARTIST:
                return await self.get_artist(parsed.id)

    async def get_stream(self, track_id: str) -> StreamInfo:
        """Ссылка на незашифрованный файл — токеном этого пользователя, без кеширования."""
        try:
            info = await self._call(
                lambda c: c.tracks_file_info(track_id, "hq", BROWSER_CODECS, "raw")
            )
        except ProviderNotFoundError as e:
            raise TrackUnavailableError from e
        except ProviderError as e:
            if isinstance(e, ProviderAuthError):
                raise
            log.info("file_info_failed_fallback_legacy", track_id=track_id)
            return await self._legacy_stream(track_id)
        d = info.download_info if info is not None else None
        if d is None:
            raise TrackUnavailableError
        if d.quality == "preview":
            # Без Плюса API отдаёт 30-секундное превью — его не играем (DECISIONS D-010).
            raise SubscriptionRequiredError
        if d.transport != "raw" or d.key:
            return await self._legacy_stream(track_id)
        return StreamInfo(
            track_id=track_id,
            mode=StreamMode.DIRECT,
            url=d.url,
            mirrors=[u for u in d.urls or [] if u != d.url],
            codec=d.codec,
            bitrate=int(d.bitrate or 0),
            expires_at=stream_expiry(d.url),
        )

    async def _legacy_stream(self, track_id: str) -> StreamInfo:
        infos = await self._call(lambda c: c.tracks_download_info(track_id))
        candidates = [i for i in infos or [] if i.codec in ("mp3", "aac") and not i.preview]
        if not candidates:
            if infos:
                raise SubscriptionRequiredError
            raise TrackUnavailableError
        best = max(candidates, key=lambda i: i.bitrate_in_kbps or 0)
        url = await self._call(lambda _c: best.get_direct_link_async())
        return StreamInfo(
            track_id=track_id,
            mode=StreamMode.DIRECT,
            url=url,
            codec=best.codec,
            bitrate=int(best.bitrate_in_kbps or 0),
        )

    # ── Волна ───────────────────────────────────────────────────────────────────

    async def start_wave(
        self, seeds: list[str], recent_ids: list[str], *, incognito: bool
    ) -> WaveBatch:
        queue = recent_ids[-WAVE_QUEUE_LIMIT:] or None
        session = await self._call(
            lambda c: c.rotor_session_new(seeds, queue=queue, incognito=incognito or None)
        )
        if session is None or not session.radio_session_id:
            raise ProviderError("Яндекс Музыка не запустила волну.")
        return WaveBatch(
            session_id=session.radio_session_id,
            batch_id=session.batch_id,
            tracks=map_wave_tracks(session.sequence),
        )

    async def next_wave_tracks(self, session_id: str, recent_ids: list[str]) -> WaveBatch:
        queue = recent_ids[-WAVE_QUEUE_LIMIT:]
        batch = await self._call(lambda c: c.rotor_session_tracks(session_id, queue=queue))
        if batch is None or batch.unknown_session or batch.terminated:
            raise WaveSessionLostError
        return WaveBatch(
            session_id=session_id,
            batch_id=batch.batch_id,
            tracks=map_wave_tracks(batch.sequence),
        )

    async def send_wave_feedback(self, session_id: str, events: list[WaveFeedback]) -> None:
        if not events:
            return
        feedbacks = [wave_event(e) for e in events]
        await self._call(lambda c: c.rotor_session_feedbacks(session_id, feedbacks))

    async def get_wave_options(self) -> WaveOptions:
        async def load() -> WaveOptions:
            settings, stations = await asyncio.gather(
                self._call(lambda c: c.rotor_wave_settings("user:onyourwave")),
                self._call(lambda c: c.rotor_stations_list()),
            )
            return WaveOptions(
                settings=_wave_setting_groups(settings), stations=_wave_stations(stations)
            )

        return await self._cached(self._private, "wave-options", WAVE_OPTIONS_TTL_S, load)

    # ── Личная коллекция ────────────────────────────────────────────────────────
    # `account_uid` у клиента пуст (init не вызывается), поэтому `user_id` передаётся всегда.

    async def get_liked_track_ids(self) -> set[str]:
        async def load() -> set[str]:
            likes = await self._call(lambda c: c.users_likes_tracks(self.uid))
            return {str(s.track_id).split(":")[0] for s in (likes.tracks if likes else [])}

        return await self._cached(self._private, "liked-ids", USER_TTL_S, load)

    def _forget_likes(self) -> None:
        self._private.delete("liked-ids")
        self._private.delete("liked")

    async def like_track(self, track_id: str) -> None:
        await self._call(lambda c: c.users_likes_tracks_add(track_id, user_id=self.uid))
        self._forget_likes()

    async def unlike_track(self, track_id: str) -> None:
        await self._call(lambda c: c.users_likes_tracks_remove(track_id, user_id=self.uid))
        self._forget_likes()

    async def dislike_track(self, track_id: str) -> None:
        await self._call(lambda c: c.users_dislikes_tracks_add(track_id, user_id=self.uid))
        self._forget_likes()

    def _own_kind(self, ref: str) -> int:
        owner, _, kind = ref.partition(":")
        if owner != self.uid or not kind.isdigit():
            raise ProviderNotFoundError("Это не ваш плейлист.")
        return int(kind)

    def _forget_playlist(self, ref: str) -> None:
        self._private.delete("my-playlists")
        self._private.delete(f"playlist:{ref}")

    async def create_playlist(self, title: str) -> PlaylistSummary:
        # У библиотеки по умолчанию `public`: сборка из комнаты не должна становиться публичной.
        playlist = await self._call(
            lambda c: c.users_playlists_create(title, visibility="private", user_id=self.uid),
            retry=False,
        )
        if playlist is None:
            raise ProviderError("Не удалось создать плейлист.")
        self._private.delete("my-playlists")
        return map_playlist(playlist, self.uid)

    async def _change_playlist(
        self, ref: str, build: Callable[[Any], list[Difference]]
    ) -> PlaylistSummary:
        """Применить изменения к свежей ревизии: конфликт — перечитать и повторить.

        Запрос с неясным исходом (таймаут) вслепую не повторяем: если ревизия выросла, он дошёл.
        API принимает дубликаты молча, поэтому повтор мог бы вставить трек дважды.
        """
        kind = self._own_kind(ref)
        async with self._playlist_locks.setdefault(ref, asyncio.Lock()):
            unclear_at: int | None = None
            for _ in range(PLAYLIST_CHANGE_ATTEMPTS):
                playlist = await self._call(lambda c: c.users_playlists(kind, self.uid))
                if playlist is None:
                    raise ProviderNotFoundError
                revision = playlist.revision or 1
                if unclear_at is not None and revision > unclear_at:
                    self._forget_playlist(ref)
                    return map_playlist(playlist, self.uid)
                unclear_at = None
                try:
                    for diff in build(playlist):
                        unclear_at = revision
                        changed = await self._send_playlist_diff(kind, diff, revision)
                        unclear_at = None
                        revision = changed.revision if changed.revision else revision + 1
                        playlist = changed
                except TimedOutError:
                    continue
                except NetworkError as e:
                    unclear_at = None
                    if "wrong-revision" in str(e):
                        continue
                    raise ProviderError from e
                self._forget_playlist(ref)
                return map_playlist(playlist, self.uid)
        raise ProviderError("Плейлист часто меняется — попробуйте ещё раз.")

    async def _send_playlist_diff(self, kind: int, diff: Difference, revision: int) -> Any:
        changed = await self._call(
            lambda c: c.users_playlists_change(kind, diff.to_json(), revision, user_id=self.uid),
            retry=False,
        )
        if changed is None:
            raise ProviderError
        return changed

    async def add_to_playlist(
        self, ref: str, track_ids: list[str], *, allow_duplicate: bool
    ) -> PlaylistSummary:
        tracks = await self.get_tracks(track_ids)
        with_album = [t for t in tracks if t.album_id]
        if not with_album:
            raise TrackUnavailableError("Этот трек нельзя добавить в плейлист: у него нет альбома.")

        def build(playlist: Any) -> list[Difference]:
            existing = {_short_track_id(s) for s in playlist.tracks or []}
            chosen = with_album
            if not allow_duplicate:
                chosen = [t for t in with_album if t.id not in existing]
                if not chosen:
                    raise DuplicateTrackError
            at = int(playlist.track_count or 0)
            diffs: list[Difference] = []
            for start in range(0, len(chosen), PLAYLIST_DIFF_CHUNK):
                part = chosen[start : start + PLAYLIST_DIFF_CHUNK]
                rows: list[dict[str, str | int]] = [
                    {"id": t.id, "album_id": str(t.album_id)} for t in part
                ]
                diffs.append(Difference().add_insert(at + start, rows))
            return diffs

        return await self._change_playlist(ref, build)

    async def remove_from_playlist(self, ref: str, track_id: str) -> PlaylistSummary:
        def build(playlist: Any) -> list[Difference]:
            ids = [_short_track_id(s) for s in playlist.tracks or []]
            if track_id not in ids:
                raise ProviderNotFoundError("Этого трека уже нет в плейлисте.")
            index = ids.index(track_id)
            # Граница `to` не включается (docs/wave-spike.md).
            return [Difference().add_delete(index, index + 1)]

        return await self._change_playlist(ref, build)


def _short_track_id(short: Any) -> str:
    return str(getattr(short, "id", "") or "").split(":")[0]


def _wave_setting_groups(settings: Any) -> list[WaveOptionGroup]:
    restrictions = settings.setting_restrictions if settings is not None else None
    if restrictions is None:
        return []
    groups: list[WaveOptionGroup] = []
    for key, value in restrictions.to_dict().items():
        if not isinstance(value, dict):
            continue
        options = [
            WaveOption(
                seed=v["serialized_seed"],
                label=str(v.get("name") or v["serialized_seed"]),
                default=bool(v.get("unspecified")),
            )
            for v in value.get("possible_values") or []
            if isinstance(v, dict) and v.get("serialized_seed")
        ]
        if options:
            groups.append(WaveOptionGroup(key=key, options=options))
    return groups


def _wave_stations(stations: Iterable[Any] | None) -> list[WaveStation]:
    result: list[WaveStation] = []
    for item in stations or []:
        station = item.station
        ident = station.id if station is not None else None
        if ident is None or ident.type not in WAVE_STATION_KINDS or not ident.tag:
            continue
        result.append(
            WaveStation(kind=ident.type, id=str(ident.tag), title=station.name or str(ident.tag))
        )
    return result


def token_fingerprint(token: str) -> str:
    """Отпечаток токена для ключей кеша — сам токен в памяти пула не хранится как ключ."""
    return hashlib.sha256(token.encode()).hexdigest()[:16]
