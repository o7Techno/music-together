"""FakeProvider: локальные тестовые треки (scripts/gen_fake_audio.py) и фиктивные метаданные.

Используется в тестах, e2e и для разработки без аккаунта (`MUSIC_PROVIDER=fake`).
"""

from __future__ import annotations

from pathlib import Path

from app.providers.base import (
    AlbumSummary,
    ArtistRef,
    ArtistSummary,
    BestResult,
    EntityKind,
    PlaylistSummary,
    ProviderNotFoundError,
    SearchResult,
    StreamInfo,
    StreamMode,
    Track,
    TrackList,
    TrackUnavailableError,
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


class FakeProvider:
    """Провайдер без сети. Один экземпляр на пользователя, как и YandexProvider."""

    def __init__(self, user_key: str = "fake") -> None:
        self.user_key = user_key

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
        return [TRACKS[i] for i in track_ids if i in TRACKS]

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
        return [
            PlaylistSummary(ref=ref, title=title, owner_name="fake", track_count=len(ids))
            for ref, (title, ids) in _PLAYLISTS.items()
        ]

    async def get_liked_tracks(self) -> TrackList:
        return TrackList(
            kind="liked", id="liked", title="Мне нравится", tracks=[TRACKS[i] for i in _LIKED]
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
        track = TRACKS.get(track_id)
        if track is None:
            raise ProviderNotFoundError
        if not track.available:
            raise TrackUnavailableError
        url = f"{FAKE_MEDIA_URL}/{track_id}.mp3"
        return StreamInfo(
            track_id=track_id, mode=StreamMode.DIRECT, url=url, codec="mp3", bitrate=96
        )
