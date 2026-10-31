"""FakeProvider: локальные тестовые треки (scripts/gen_fake_audio.py) и фиктивные метаданные.

Используется в тестах, e2e и для разработки без аккаунта (`MUSIC_PROVIDER=fake`). Изменяемое
состояние (лайки, плейлисты, фидбек волны, управляемые сбои) живёт в `FakeWorld`: провайдер
создаётся на каждый вызов, а мир — один на `ProviderFactory`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

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

FAKE_MEDIA_DIR = Path(__file__).resolve().parents[2] / "fake_media"
FAKE_MEDIA_URL = "/media/fake"

_ARTISTS = {
    "a1": ArtistRef(id="a1", name="Метроном"),
    "a2": ArtistRef(id="a2", name="Тон-генератор"),
    "a3": ArtistRef(id="a3", name="Щелчки и Ко"),
}

# id, название, длительность (с), артист, альбом. Длительности совпадают с gen_fake_audio.py.
_TRACK_ROWS: list[tuple[str, str, int, str, str]] = [
    ("fake-1", "Тридцать щелчков", 30, "a1", "al1"),
    ("fake-2", "Сорок пять", 45, "a1", "al1"),
    ("fake-3", "Минута ровно", 60, "a1", "al1"),
    ("fake-4", "Семьдесят пять", 75, "a2", "al2"),
    ("fake-5", "Полторы минуты", 90, "a2", "al2"),
    ("fake-6", "Две минуты", 120, "a2", "al2"),
    ("fake-7", "Сто пятьдесят", 150, "a3", "al3"),
    ("fake-8", "Три минуты", 180, "a3", "al3"),
    ("fake-9", "Четыре минуты", 240, "a3", "al3"),
    ("fake-10", "Короткий", 20, "a1", "al1"),
]

_ALBUMS = {
    "al1": ("Ритм", "a1", 2024),
    "al2": ("Частоты", "a2", 2025),
    "al3": ("Синхрон", "a3", 2026),
}

UNAVAILABLE_TRACK_ID = "fake-unavailable"


def _cover(seed: str) -> str:
    # Плейсхолдер без внешних запросов: SVG-обложка генерируется фронтом по seed.
    return f"fake://{seed}/{{size}}"


def _track(row: tuple[str, str, int, str, str]) -> Track:
    track_id, title, duration_s, artist_id, album_id = row
    return Track(
        id=track_id,
        title=title,
        artists=[_ARTISTS[artist_id]],
        album_id=album_id,
        album_title=_ALBUMS[album_id][0],
        duration_ms=duration_s * 1000,
        cover_url=_cover(album_id),
    )


TRACKS: dict[str, Track] = {row[0]: _track(row) for row in _TRACK_ROWS}
TRACKS[UNAVAILABLE_TRACK_ID] = Track(
    id=UNAVAILABLE_TRACK_ID,
    title="Недоступный трек",
    artists=[_ARTISTS["a3"]],
    duration_ms=60_000,
    cover_url=_cover("x"),
    available=False,
)


def _album_summary(album_id: str) -> AlbumSummary:
    title, artist_id, year = _ALBUMS[album_id]
    tracks = [t for t in TRACKS.values() if t.album_id == album_id]
    return AlbumSummary(
        id=album_id,
        title=title,
        artists=[_ARTISTS[artist_id]],
        year=year,
        track_count=len(tracks),
        cover_url=_cover(album_id),
    )


_PLAYLISTS: dict[str, tuple[str, list[str]]] = {
    "fake:1": ("Все тестовые треки", [row[0] for row in _TRACK_ROWS]),
    "fake:2": ("Короткие", ["fake-10", "fake-1", "fake-2"]),
}
_LIKED = ["fake-3", "fake-5", "fake-8"]


WAVE_PREFIX = "fake-wave-"
WAVE_BATCH_SIZE = 5
_FILE_ROWS = [row for row in _TRACK_ROWS if row[2] <= 60]
"""Для волны — короткие файлы: e2e дожидается перехода между треками."""


def _wave_track(track_id: str) -> Track | None:
    """Бесконечный каталог волны: уникальные id над десятком тестовых файлов."""
    if not track_id.startswith(WAVE_PREFIX):
        return None
    try:
        number = int(track_id.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return None
    base = _track(_FILE_ROWS[number % len(_FILE_ROWS)])
    return base.model_copy(update={"id": track_id, "title": f"Волна {number} · {base.title}"})


def _lookup(track_id: str) -> Track | None:
    return TRACKS.get(track_id) or _wave_track(track_id)


def _file_id(track_id: str) -> str:
    if not track_id.startswith(WAVE_PREFIX):
        return track_id
    return _FILE_ROWS[int(track_id.rsplit("-", 1)[1]) % len(_FILE_ROWS)][0]


@dataclass
class FakePlaylist:
    title: str
    track_ids: list[str] = field(default_factory=list)
    revision: int = 1


@dataclass
class FakeSession:
    user_key: str
    seeds: list[str]
    incognito: bool
    next_number: int


@dataclass
class FakeUser:
    liked: list[str] = field(default_factory=lambda: list(_LIKED))
    disliked: set[str] = field(default_factory=set)
    playlists: dict[str, FakePlaylist] = field(default_factory=dict)
    next_kind: int = 100


@dataclass
class FakeWorld:
    """Общее состояние фейка на процесс. Тесты управляют им и читают записанный фидбек."""

    users: dict[str, FakeUser] = field(default_factory=dict)
    sessions: dict[str, FakeSession] = field(default_factory=dict)
    feedback: list[tuple[str, str, WaveFeedback]] = field(default_factory=list)
    """(пользователь, сессия, событие) — всё, что получила фейковая волна."""
    wave_failures: int = 0
    """Сколько следующих запросов порции упадёт с ошибкой сервиса."""
    wave_auth_failure: bool = False
    empty_batches: int = 0
    revision_conflicts: int = 0
    """Сколько следующих изменений плейлиста получат конфликт ревизии."""
    unavailable_for: dict[str, set[str]] = field(default_factory=dict)
    """Пользователь → недоступные ему треки."""
    wave_requests: int = 0
    wave_gate: object | None = None
    """asyncio.Event: если задан, запросы порций ждут его (тест «пропуск во время дозагрузки»)."""

    def user(self, key: str) -> FakeUser:
        return self.users.setdefault(key, FakeUser())

    def lose_sessions(self) -> None:
        self.sessions.clear()


class FakeProvider:
    """Провайдер без сети. Один экземпляр на пользователя, как и YandexProvider."""

    def __init__(self, user_key: str = "fake", world: FakeWorld | None = None) -> None:
        self.user_key = user_key
        self.world = world or FakeWorld()

    @property
    def _me(self) -> FakeUser:
        return self.world.user(self.user_key)

    async def search(self, query: str) -> SearchResult:
        q = query.strip().lower()
        if not q:
            return SearchResult()
        tracks = [
            t
            for t in TRACKS.values()
            if t.available
            and (q in t.title.lower() or any(q in a.name.lower() for a in t.artists) or q == "*")
        ]
        albums = [_album_summary(a) for a, v in _ALBUMS.items() if q in v[0].lower() or q == "*"]
        artists = [
            ArtistSummary(id=a.id, name=a.name, cover_url=_cover(a.id))
            for a in _ARTISTS.values()
            if q in a.name.lower() or q == "*"
        ]
        playlists = [
            PlaylistSummary(ref=ref, title=title, owner_name="fake", track_count=len(ids))
            for ref, (title, ids) in _PLAYLISTS.items()
            if q in title.lower() or q == "*"
        ]
        best: BestResult | None = None
        if tracks:
            best = BestResult(kind=EntityKind.TRACK, track=tracks[0])
        elif artists:
            best = BestResult(kind=EntityKind.ARTIST, artist=artists[0])
        return SearchResult(
            best=best, tracks=tracks, albums=albums, artists=artists, playlists=playlists
        )

    async def get_tracks(self, track_ids: list[str]) -> list[Track]:
        return [t for t in (_lookup(i) for i in track_ids) if t is not None]

    async def get_album(self, album_id: str) -> TrackList:
        if album_id not in _ALBUMS:
            raise ProviderNotFoundError
        summary = _album_summary(album_id)
        return TrackList(
            kind=EntityKind.ALBUM,
            id=album_id,
            title=summary.title,
            subtitle=", ".join(a.name for a in summary.artists),
            cover_url=summary.cover_url,
            tracks=[t for t in TRACKS.values() if t.album_id == album_id],
        )

    async def get_playlist(self, ref: str) -> TrackList:
        own = self._me.playlists.get(ref)
        if own is not None:
            return TrackList(
                kind=EntityKind.PLAYLIST,
                id=ref,
                title=own.title,
                subtitle="fake",
                tracks=await self.get_tracks(own.track_ids),
            )
        if ref not in _PLAYLISTS:
            raise ProviderNotFoundError
        title, ids = _PLAYLISTS[ref]
        return TrackList(
            kind=EntityKind.PLAYLIST,
            id=ref,
            title=title,
            subtitle="fake",
            tracks=[TRACKS[i] for i in ids],
        )

    async def get_artist(self, artist_id: str) -> TrackList:
        artist = _ARTISTS.get(artist_id)
        if artist is None:
            raise ProviderNotFoundError
        return TrackList(
            kind=EntityKind.ARTIST,
            id=artist_id,
            title=artist.name,
            cover_url=_cover(artist_id),
            tracks=[t for t in TRACKS.values() if any(a.id == artist_id for a in t.artists)],
            albums=[_album_summary(a) for a, v in _ALBUMS.items() if v[1] == artist_id],
        )

    async def get_user_playlists(self) -> list[PlaylistSummary]:
        shared = [
            PlaylistSummary(ref=ref, title=title, owner_name="fake", track_count=len(ids))
            for ref, (title, ids) in _PLAYLISTS.items()
        ]
        own = [self._summary(ref, p) for ref, p in self._me.playlists.items()]
        return [*own, *shared]

    def _summary(self, ref: str, playlist: FakePlaylist) -> PlaylistSummary:
        return PlaylistSummary(
            ref=ref,
            title=playlist.title,
            owner_name="fake",
            track_count=len(playlist.track_ids),
            editable=True,
        )

    async def get_liked_tracks(self) -> TrackList:
        return TrackList(
            kind="liked",
            id="liked",
            title="Мне нравится",
            tracks=await self.get_tracks(self._me.liked),
        )

    async def get_liked_albums(self) -> list[AlbumSummary]:
        return [_album_summary("al2")]

    async def resolve(self, link: ParsedLink) -> TrackList:
        """Ссылки Яндекса с маленькими числовыми id отображаются на фейковый каталог:
        `/track/3` → fake-3, `/album/1` → al1, `/artist/2` → a2, `/users/x/playlists/1` → fake:1.
        Так e2e проверяет настоящий парсер ссылок без сети."""
        match link.kind:
            case EntityKind.TRACK:
                track = TRACKS.get(f"fake-{link.id}")
                if track is None:
                    raise ProviderNotFoundError
                return TrackList(
                    kind=EntityKind.TRACK,
                    id=track.id,
                    title=track.title,
                    subtitle=", ".join(a.name for a in track.artists),
                    cover_url=track.cover_url,
                    tracks=[track],
                )
            case EntityKind.ALBUM:
                return await self.get_album(f"al{link.id}")
            case EntityKind.ARTIST:
                return await self.get_artist(f"a{link.id}")
            case EntityKind.PLAYLIST:
                return await self.get_playlist(f"fake:{link.id.rsplit(':', 1)[-1]}")

    async def get_stream(self, track_id: str) -> StreamInfo:
        track = _lookup(track_id)
        if track is None:
            raise ProviderNotFoundError
        if not track.available or track_id in self.world.unavailable_for.get(self.user_key, ()):
            raise TrackUnavailableError
        url = f"{FAKE_MEDIA_URL}/{_file_id(track_id)}.mp3"
        return StreamInfo(
            track_id=track_id, mode=StreamMode.DIRECT, url=url, codec="mp3", bitrate=96
        )

    # ── Волна ───────────────────────────────────────────────────────────────────

    async def _wave_gate(self) -> None:
        self.world.wave_requests += 1
        gate = self.world.wave_gate
        if gate is not None:
            await gate.wait()  # type: ignore[attr-defined]  # asyncio.Event из теста
        if self.world.wave_auth_failure:
            raise ProviderAuthError
        if self.world.wave_failures > 0:
            self.world.wave_failures -= 1
            raise ProviderError

    def _batch(self, session_id: str, recent_ids: list[str]) -> WaveBatch:
        session = self.world.sessions[session_id]
        if self.world.empty_batches > 0:
            self.world.empty_batches -= 1
            return WaveBatch(session_id=session_id, batch_id="empty", tracks=[])
        digest = hashlib.sha256(",".join(session.seeds).encode()).hexdigest()[:6]
        recent = set(recent_ids)
        tracks: list[Track] = []
        while len(tracks) < WAVE_BATCH_SIZE:
            number = session.next_number
            session.next_number += 1
            track = _wave_track(f"{WAVE_PREFIX}{digest}-{number}")
            if track is not None and track.id not in recent:
                tracks.append(track)
        return WaveBatch(
            session_id=session_id, batch_id=f"batch-{session.next_number}", tracks=tracks
        )

    async def start_wave(
        self, seeds: list[str], recent_ids: list[str], *, incognito: bool
    ) -> WaveBatch:
        await self._wave_gate()
        session_id = f"fake-session-{self.world.wave_requests}"
        self.world.sessions[session_id] = FakeSession(self.user_key, seeds, incognito, 0)
        return self._batch(session_id, recent_ids)

    async def next_wave_tracks(self, session_id: str, recent_ids: list[str]) -> WaveBatch:
        await self._wave_gate()
        if session_id not in self.world.sessions:
            raise WaveSessionLostError
        return self._batch(session_id, recent_ids)

    async def send_wave_feedback(self, session_id: str, events: list[WaveFeedback]) -> None:
        self.world.feedback.extend((self.user_key, session_id, e) for e in events)

    async def get_wave_options(self) -> WaveOptions:
        return WaveOptions(
            settings=[
                WaveOptionGroup(
                    key="diversity",
                    options=[
                        WaveOption(seed="settingDiversity:default", label="Любое", default=True),
                        WaveOption(seed="settingDiversity:favorite", label="Любимое"),
                        WaveOption(seed="settingDiversity:discover", label="Незнакомое"),
                    ],
                ),
                WaveOptionGroup(
                    key="language",
                    options=[
                        WaveOption(seed="settingLanguage:any", label="Любой", default=True),
                        WaveOption(seed="settingLanguage:russian", label="Русский"),
                    ],
                ),
            ],
            stations=[
                WaveStation(kind="mood", id="happy", title="Весёлое"),
                WaveStation(kind="activity", id="workout", title="Спорт"),
                WaveStation(kind="genre", id="rock", title="Рок"),
            ],
        )

    # ── Личная коллекция ────────────────────────────────────────────────────────

    async def get_liked_track_ids(self) -> set[str]:
        return set(self._me.liked)

    async def like_track(self, track_id: str) -> None:
        self._me.disliked.discard(track_id)
        if track_id not in self._me.liked:
            self._me.liked.append(track_id)

    async def unlike_track(self, track_id: str) -> None:
        if track_id in self._me.liked:
            self._me.liked.remove(track_id)

    async def dislike_track(self, track_id: str) -> None:
        self._me.disliked.add(track_id)
        if track_id in self._me.liked:
            self._me.liked.remove(track_id)

    async def create_playlist(self, title: str) -> PlaylistSummary:
        me = self._me
        ref = f"{self.user_key}:{me.next_kind}"
        me.next_kind += 1
        me.playlists[ref] = FakePlaylist(title)
        return self._summary(ref, me.playlists[ref])

    def _own_playlist(self, ref: str) -> FakePlaylist:
        playlist = self._me.playlists.get(ref)
        if playlist is None:
            raise ProviderNotFoundError("Это не ваш плейлист.")
        return playlist

    def _conflict_absorbed(self, playlist: FakePlaylist) -> None:
        """Конфликт ревизии: настоящий провайдер перечитывает и повторяет — здесь то же самое."""
        while self.world.revision_conflicts > 0:
            self.world.revision_conflicts -= 1
            playlist.revision += 1

    async def add_to_playlist(
        self, ref: str, track_ids: list[str], *, allow_duplicate: bool
    ) -> PlaylistSummary:
        playlist = self._own_playlist(ref)
        self._conflict_absorbed(playlist)
        chosen = [t.id for t in await self.get_tracks(track_ids)]
        if not allow_duplicate:
            chosen = [i for i in chosen if i not in playlist.track_ids]
            if not chosen:
                raise DuplicateTrackError
        playlist.track_ids.extend(chosen)
        playlist.revision += 1
        return self._summary(ref, playlist)

    async def remove_from_playlist(self, ref: str, track_id: str) -> PlaylistSummary:
        playlist = self._own_playlist(ref)
        self._conflict_absorbed(playlist)
        if track_id not in playlist.track_ids:
            raise ProviderNotFoundError("Этого трека уже нет в плейлисте.")
        playlist.track_ids.remove(track_id)
        playlist.revision += 1
        return self._summary(ref, playlist)
