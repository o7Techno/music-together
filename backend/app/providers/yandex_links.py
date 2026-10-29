"""Парсер ссылок Яндекс Музыки (SPEC §4.4).

Поддерживаются (проверено в спайке на реальных ссылках, docs/yandex-spike.md):
- трек: `/album/{albumId}/track/{trackId}`, `/track/{trackId}`
- альбом: `/album/{albumId}`
- плейлист: `/users/{login}/playlists/{kind}`, `/playlists/{uuid}` (`ar.…`, `lk.…` или голый UUID)
- исполнитель: `/artist/{artistId}` (в т.ч. `/artist/{id}/tracks`, `/albums`)
- домены `music.yandex.{ru,com,by,kz,uz}`, с/без схемы и `www.`, с query (UTM, `ref_id`) и якорями;
  ссылки «Поделиться» из мобильного приложения (`?ref_id=…&utm_medium=copy_link`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from app.providers.base import EntityKind

_HOST = re.compile(r"^(?:www\.)?music\.yandex\.(?:ru|com|by|kz|uz)$", re.IGNORECASE)
_ID = r"(\d{1,12})"
_UUID = r"((?:[a-z]{2}\.)?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
_LOGIN = r"([A-Za-z0-9._@-]{1,64})"

_ROUTES: list[tuple[re.Pattern[str], EntityKind]] = [
    (re.compile(rf"^/album/{_ID}/track/{_ID}/?$"), EntityKind.TRACK),
    (re.compile(rf"^/track/{_ID}/?$"), EntityKind.TRACK),
    (re.compile(rf"^/album/{_ID}/?$"), EntityKind.ALBUM),
    (re.compile(rf"^/users/{_LOGIN}/playlists/{_ID}/?$"), EntityKind.PLAYLIST),
    (re.compile(rf"^/playlists?/{_UUID}/?$", re.IGNORECASE), EntityKind.PLAYLIST),
    (
        re.compile(rf"^/artist/{_ID}(?:/(?:tracks|albums|info|similar|discography))?/?$"),
        EntityKind.ARTIST,
    ),
]

_URL_IN_TEXT = re.compile(
    r"(?:https?://)?(?:www\.)?music\.yandex\.(?:ru|com|by|kz|uz)/[^\s<>\"']+", re.IGNORECASE
)


@dataclass(frozen=True)
class ParsedLink:
    kind: EntityKind
    id: str
    """track: id трека; album/artist: id; playlist: `owner:kind` или UUID."""
    album_id: str | None = None


def parse_link(raw: str) -> ParsedLink | None:  # noqa: PLR0911 — плоский разбор маршрутов
    """Разобрать одну ссылку. Мусор и чужие домены → None (без исключений)."""
    text = raw.strip().strip("<>\"'")
    if not text or len(text) > 2048 or any(c.isspace() for c in text):
        return None
    if "://" not in text:
        text = "https://" + text
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not _HOST.match(parts.hostname or ""):
        return None
    path = unquote(parts.path) or "/"
    for pattern, kind in _ROUTES:
        m = pattern.match(path)
        if m is None:
            continue
        groups = m.groups()
        if kind is EntityKind.TRACK and len(groups) == 2:
            return ParsedLink(kind, groups[1], album_id=groups[0])
        if kind is EntityKind.PLAYLIST and len(groups) == 2:
            return ParsedLink(kind, f"{groups[0]}:{groups[1]}")
        if kind is EntityKind.PLAYLIST:
            return ParsedLink(kind, groups[0].lower())
        return ParsedLink(kind, groups[0])
    return None


def extract_links(text: str, limit: int = 50) -> list[ParsedLink]:
    """Все ссылки Яндекс Музыки из произвольного текста (несколько ссылок, по одной на строку
    или вперемешку с текстом). Дубликаты убираются, порядок сохраняется."""
    seen: set[ParsedLink] = set()
    result: list[ParsedLink] = []
    for match in _URL_IN_TEXT.finditer(text[:100_000]):
        parsed = parse_link(match.group(0).rstrip(".,;:!?)"))
        if parsed is not None and parsed not in seen:
            seen.add(parsed)
            result.append(parsed)
            if len(result) >= limit:
                break
    return result
