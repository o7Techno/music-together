"""YandexProvider на подменённом клиенте библиотеки: маппинг, политика ретраев, ссылки на аудио."""

from __future__ import annotations

import time
from types import SimpleNamespace as NS  # noqa: N814 — короткое имя для фикстур
from typing import Any

import pytest
from yandex_music.exceptions import BadRequestError, NetworkError, TimedOutError, UnauthorizedError

from app.core.ratelimit import RateLimiter
from app.providers import yandex as ym
from app.providers.base import (
    EntityKind,
    ProviderAuthError,
    ProviderError,
    ProviderNotFoundError,
    StreamMode,
    SubscriptionRequiredError,
    TrackUnavailableError,
)
from app.providers.yandex import TTLCache, YandexProvider, map_track, stream_expiry
from app.providers.yandex_links import ParsedLink


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ym, "RETRY_DELAYS_S", (0.0, 0.0))


def raw_track(i: int, *, available: bool = True) -> NS:
    return NS(
        id=i,
        title=f"Song {i}",
        version=None,
        artists=[NS(id=1, name="Radiohead")],
        albums=[NS(id=10, title="Pablo Honey")],
        duration_ms=237_000,
        cover_uri="avatars.yandex.net/get-music-content/1/a.b/%%",
        og_image=None,
        available=available,
    )


def file_info(**kw: Any) -> NS:
    base = {
        "quality": "hq",
        "codec": "aac-mp4",
        "bitrate": 192,
        "transport": "raw",
        "key": None,
        "url": "https://strm-1.strm.yandex.net/music-v2/raw/ysign1=abc,lid=1,ts=6af112c7/0/1/2.mp4",
        "urls": [
            "https://strm-1.strm.yandex.net/music-v2/raw/ysign1=abc,lid=1,ts=6af112c7/0/1/2.mp4",
            "https://strm-2.strm.yandex.net/x.mp4",
        ],
    }
    return NS(download_info=NS(**(base | kw)))


class FakeClient:
    """Минимальный двойник ClientAsync: методы задаются тестом, вызовы считаются."""

    def __init__(self, **methods: Any) -> None:
        self.calls: dict[str, int] = {}
        for name, impl in methods.items():
            setattr(self, name, self._wrap(name, impl))

    def _wrap(self, name: str, impl: Any) -> Any:
        async def method(*args: Any, **kwargs: Any) -> Any:
            self.calls[name] = self.calls.get(name, 0) + 1
            result = impl(*args, **kwargs) if callable(impl) else impl
            if isinstance(result, Exception):
                raise result
            return result

        return method


def provider(client: FakeClient, **kw: Any) -> YandexProvider:
    return YandexProvider(
        user_key="u1",
        uid="42",
        token="tok",
        proxy_url=None,
        public_cache=TTLCache(),
        limiter=RateLimiter(1000, 1000, time.monotonic),
        client_factory=lambda _tok: client,
        **kw,
    )


def test_map_track_builds_cover_template_and_flags() -> None:
    t = map_track(raw_track(7, available=False))
    assert t is not None
    assert t.id == "7"
    assert t.album_id == "10"
    assert t.cover_url == "https://avatars.yandex.net/get-music-content/1/a.b/{size}"
    assert t.available is False
    assert map_track(NS(id=None, title="x")) is None


def test_stream_expiry_parses_hex_ts() -> None:
    exp = stream_expiry("https://strm/raw/ysign1=a,lid=1,ts=6af112c7/0/1/2.mp4")
    assert exp is not None
    assert exp.year == 2026
    assert stream_expiry("https://example.com/x.mp3") is None


async def test_get_stream_returns_raw_link_with_mirrors() -> None:
    client = FakeClient(tracks_file_info=file_info())
    info = await provider(client).get_stream("7")
    assert info.mode is StreamMode.DIRECT
    assert info.codec == "aac-mp4"
    assert info.mirrors == ["https://strm-2.strm.yandex.net/x.mp4"]
    assert info.expires_at is not None


async def test_preview_means_subscription_required() -> None:
    client = FakeClient(tracks_file_info=file_info(quality="preview", codec="mp3", bitrate=128))
    with pytest.raises(SubscriptionRequiredError):
        await provider(client).get_stream("7")


async def test_encrypted_transport_falls_back_to_legacy_mp3() -> None:
    legacy = NS(
        codec="mp3",
        bitrate_in_kbps=192,
        preview=False,
        get_direct_link_async=lambda: _async_value("https://s.yandex.net/get-mp3/x.mp3"),
    )
    client = FakeClient(
        tracks_file_info=file_info(transport="encraw", key="00ff"),
        tracks_download_info=[legacy],
    )
    info = await provider(client).get_stream("7")
    assert info.url.endswith("x.mp3")
    assert info.codec == "mp3"


async def _async_value(v: str) -> str:
    return v


async def test_unknown_track_stream_is_unavailable() -> None:
    client = FakeClient(tracks_file_info=BadRequestError("bad"))
    with pytest.raises(TrackUnavailableError):
        await provider(client).get_stream("999")


async def test_network_errors_are_retried_then_succeed() -> None:
    attempts = iter([TimedOutError(), NetworkError("502"), [raw_track(1)]])
    client = FakeClient(tracks=lambda _ids: next(attempts))
    tracks = await provider(client).get_tracks(["1"])
    assert [t.id for t in tracks] == ["1"]
    assert client.calls["tracks"] == 3


async def test_network_errors_exhaust_retries() -> None:
    client = FakeClient(search=NetworkError("503"))
    with pytest.raises(ProviderError) as exc:
        await provider(client).search("radiohead")
    assert exc.value.code == "provider_error"
    assert client.calls["search"] == 3


async def test_client_errors_are_not_retried() -> None:
    client = FakeClient(albums_with_tracks=BadRequestError("invalid id"))
    with pytest.raises(ProviderNotFoundError):
        await provider(client).get_album("x")
    assert client.calls["albums_with_tracks"] == 1


async def test_unauthorized_refreshes_token_once() -> None:
    old = FakeClient(tracks=UnauthorizedError("expired"))
    new = FakeClient(tracks=[raw_track(1)])
    clients = {"tok": old, "fresh": new}
    refreshes: list[int] = []

    async def refresher() -> str | None:
        refreshes.append(1)
        return "fresh"

    p = YandexProvider(
        user_key="u1",
        uid="42",
        token="tok",
        proxy_url=None,
        public_cache=TTLCache(),
        limiter=RateLimiter(1000, 1000, time.monotonic),
        refresher=refresher,
        client_factory=lambda tok: clients[tok],
    )
    assert [t.id for t in await p.get_tracks(["1"])] == ["1"]
    assert refreshes == [1]


async def test_unauthorized_without_refresh_asks_to_relogin() -> None:
    client = FakeClient(search=UnauthorizedError("revoked"))

    async def refresher() -> str | None:
        return None

    with pytest.raises(ProviderAuthError) as exc:
        await provider(client, refresher=refresher).search("x")
    assert "войдите заново" in exc.value.message


async def test_metadata_is_cached_but_streams_are_not() -> None:
    album = NS(
        id=10,
        title="Pablo Honey",
        artists=[NS(id=1, name="Radiohead")],
        year=1993,
        track_count=2,
        cover_uri=None,
        og_image=None,
        volumes=[[raw_track(1), raw_track(2)]],
    )
    client = FakeClient(albums_with_tracks=album, tracks_file_info=file_info())
    p = provider(client)
    first = await p.get_album("10")
    second = await p.get_album("10")
    assert first == second
    assert [t.id for t in first.tracks] == ["1", "2"]
    assert client.calls["albums_with_tracks"] == 1
    await p.get_stream("1")
    await p.get_stream("1")
    assert client.calls["tracks_file_info"] == 2


async def test_playlist_by_owner_kind_and_uuid_fill_missing_tracks() -> None:
    playlist = NS(
        kind=3,
        title="Мой плейлист",
        owner=NS(uid=42, login="me", name="Я"),
        playlist_uuid="lk.x",
        track_count=2,
        cover=None,
        cover_uri=None,
        og_image=None,
        tracks=[NS(track=raw_track(1), id="1"), NS(track=None, id="2:20")],
    )
    client = FakeClient(
        users_playlists=playlist,
        playlist=playlist,
        tracks=lambda ids: [raw_track(int(i)) for i in ids],
    )
    p = provider(client)
    by_kind = await p.get_playlist("42:3")
    assert [t.id for t in by_kind.tracks] == ["1", "2"]
    assert by_kind.id == "42:3"
    by_uuid = await p.get_playlist("ar.273c2610-f97c-452c-9b76-6ffe77b2f5ce")
    assert len(by_uuid.tracks) == 2
    with pytest.raises(ProviderNotFoundError):
        await p.get_playlist("42:abc")


async def test_resolve_track_link() -> None:
    client = FakeClient(tracks=[raw_track(26360014)])
    result = await provider(client).resolve(ParsedLink(EntityKind.TRACK, "26360014", "3135476"))
    assert result.kind is EntityKind.TRACK
    assert result.tracks[0].id == "26360014"


async def test_search_maps_best_result() -> None:
    sr = NS(
        best=NS(
            type="artist",
            result=NS(id=1, name="Radiohead", cover=None, cover_uri=None, og_image=None),
        ),
        tracks=NS(results=[raw_track(1)]),
        albums=None,
        artists=None,
        playlists=None,
    )
    result = await provider(FakeClient(search=sr)).search("радиохед")
    assert result.best is not None
    assert result.best.kind is EntityKind.ARTIST
    assert [t.id for t in result.tracks] == ["1"]
