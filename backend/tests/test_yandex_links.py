import pytest

from app.providers.base import EntityKind
from app.providers.yandex_links import ParsedLink, extract_links, parse_link

T, AL, PL, AR = EntityKind.TRACK, EntityKind.ALBUM, EntityKind.PLAYLIST, EntityKind.ARTIST


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        # Реальные ссылки «Поделиться» из мобильного приложения владельца (спайк).
        (
            "https://music.yandex.ru/album/3135476/track/26360014?ref_id=1F79053F-0800-465D-96DC-B0B6F6706A3B&utm_medium=copy_link",
            ParsedLink(T, "26360014", "3135476"),
        ),
        (
            "https://music.yandex.ru/album/44454101/track/157077943?ref_id=CA72DC27-9A63-4CC6-8E8C-43E846852E79&utm_medium=copy_link",
            ParsedLink(T, "157077943", "44454101"),
        ),
        # Треки
        ("https://music.yandex.ru/album/3389005/track/330765", ParsedLink(T, "330765", "3389005")),
        ("music.yandex.ru/album/3389005/track/330765", ParsedLink(T, "330765", "3389005")),
        ("http://www.music.yandex.com/album/1/track/2/", ParsedLink(T, "2", "1")),
        ("https://music.yandex.ru/track/330765", ParsedLink(T, "330765")),
        ("https://music.yandex.by/track/330765?utm_source=web#lyrics", ParsedLink(T, "330765")),
        ("  https://MUSIC.YANDEX.KZ/track/330765  ", ParsedLink(T, "330765")),
        # Альбомы
        ("https://music.yandex.ru/album/3389005", ParsedLink(AL, "3389005")),
        ("https://music.yandex.uz/album/3389005/?utm_medium=copy_link", ParsedLink(AL, "3389005")),
        # Плейлисты
        (
            "https://music.yandex.ru/users/yamusic-bestsongs/playlists/36825",
            ParsedLink(PL, "yamusic-bestsongs:36825"),
        ),
        (
            "https://music.yandex.ru/users/some.user@ya.ru/playlists/3",
            ParsedLink(PL, "some.user@ya.ru:3"),
        ),
        (
            "https://music.yandex.ru/playlists/ar.273c2610-f97c-452c-9b76-6ffe77b2f5ce",
            ParsedLink(PL, "ar.273c2610-f97c-452c-9b76-6ffe77b2f5ce"),
        ),
        (
            "https://music.yandex.ru/playlists/lk.273C2610-F97C-452C-9B76-6FFE77B2F5CE?utm_source=x",
            ParsedLink(PL, "lk.273c2610-f97c-452c-9b76-6ffe77b2f5ce"),
        ),
        (
            "https://music.yandex.ru/playlists/273c2610-f97c-452c-9b76-6ffe77b2f5ce",
            ParsedLink(PL, "273c2610-f97c-452c-9b76-6ffe77b2f5ce"),
        ),
        # Исполнители
        ("https://music.yandex.ru/artist/36825", ParsedLink(AR, "36825")),
        ("https://music.yandex.ru/artist/36825/tracks", ParsedLink(AR, "36825")),
        ("https://music.yandex.com/artist/36825/albums?x=1", ParsedLink(AR, "36825")),
    ],
)
def test_parse_valid_links(url: str, expected: ParsedLink) -> None:
    assert parse_link(url) == expected


@pytest.mark.parametrize(
    "garbage",
    [
        "",
        "   ",
        "радиохед",
        "https://music.yandex.ru/",
        "https://music.yandex.ru/home",
        "https://music.yandex.ru/album/",
        "https://music.yandex.ru/album/abc",
        "https://music.yandex.ru/album/1/track/",
        "https://music.yandex.ru/track/12a",
        "https://music.yandex.ru/users/x/playlists/abc",
        "https://music.yandex.ru/playlists/not-a-uuid",
        "https://music.yandex.ru/artist/1/../../etc",
        "https://music.yandex.de/track/1",
        "https://music.yandex.ru.evil.com/track/1",
        "https://evil.com/music.yandex.ru/track/1",
        "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC",
        "ftp://music.yandex.ru/track/1",
        "javascript:alert(1)",
        "https://music.yandex.ru/track/1 https://music.yandex.ru/track/2",
        "https://music.yandex.ru/track/" + "1" * 30,
        "x" * 5000,
    ],
)
def test_parse_garbage_returns_none(garbage: str) -> None:
    assert parse_link(garbage) is None


def test_extract_multiple_links_from_text() -> None:
    text = """Послушай вот это:
    https://music.yandex.ru/album/1/track/2?utm_medium=copy_link,
    и альбом music.yandex.ru/album/1 — огонь!
    https://music.yandex.ru/album/1/track/2
    <https://music.yandex.ru/playlists/ar.273c2610-f97c-452c-9b76-6ffe77b2f5ce>
    https://example.com/track/5
    """
    assert extract_links(text) == [
        ParsedLink(T, "2", "1"),
        ParsedLink(AL, "1"),
        ParsedLink(PL, "ar.273c2610-f97c-452c-9b76-6ffe77b2f5ce"),
    ]


def test_extract_links_limit() -> None:
    text = "\n".join(f"https://music.yandex.ru/track/{i}" for i in range(100))
    assert len(extract_links(text, limit=10)) == 10
