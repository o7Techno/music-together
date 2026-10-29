"""Спайк по Яндекс Музыке (SPEC §6.1).

Запуск (из каталога backend, чтобы использовать его окружение):

    cd backend
    uv run python ../scripts/spike_yandex.py auth      # Device Flow → токен в ../.env (YM_TOKEN), не печатается
    uv run python ../scripts/spike_yandex.py run       # полный прогон с токеном
    uv run python ../scripts/spike_yandex.py recheck   # повторная проверка сохранённых ссылок (время жизни)
    uv run python ../scripts/spike_yandex.py links URL [URL...]  # разбор реальных ссылок «Поделиться»

Токен берётся из переменной окружения YM_TOKEN или из файла `.env` в корне репозитория.
Токен никогда не печатается и не пишется в отчёты. Подписанные ссылки на аудио в отчётах
обрезаются до хоста и пути без подписи; полные ссылки хранятся только в `scripts/.spike-out/`
(в .gitignore) для `recheck` и браузерного теста.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from yandex_music import ClientAsync
from yandex_music.exceptions import YandexMusicError

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "scripts" / ".spike-out"
ENV_FILE = ROOT / ".env"

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
OTHER_UA = "curl/8.9.1"
ORIGIN = "http://localhost:5173"

# Магические байты контейнеров — чтобы проверить, что `raw` действительно не зашифрован.
MAGIC = [
    (b"ID3", "mp3 (ID3)"),
    (b"\xff\xfb", "mp3 frame"),
    (b"\xff\xf3", "mp3 frame"),
    (b"\xff\xf2", "mp3 frame"),
    (b"\xff\xf1", "aac ADTS"),
    (b"\xff\xf9", "aac ADTS"),
    (b"fLaC", "flac"),
]


def sniff(data: bytes) -> str:
    if len(data) >= 8 and data[4:8] == b"ftyp":
        return f"mp4 (ftyp {data[8:12].decode('latin1', 'replace')})"
    for magic, name in MAGIC:
        if data.startswith(magic):
            return name
    return f"unknown/encrypted? first bytes={data[:8].hex()}"


def redact_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{re.sub(r'/[0-9a-f]{32}/', '/<sign>/', p.path)[:80]}…"


def load_token() -> str:
    token = os.environ.get("YM_TOKEN", "").strip()
    if not token and ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("YM_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not token:
        sys.exit(
            "YM_TOKEN не найден: задайте переменную окружения или выполните `auth` (запишет в .env)"
        )
    return token


def make_request_kwargs() -> dict[str, Any]:
    proxy = os.environ.get("YM_PROXY_URL") or None
    return {"proxy_url": proxy} if proxy else {}


@dataclass
class Report:
    sections: dict[str, Any] = field(default_factory=dict)

    def put(self, key: str, value: Any) -> None:
        self.sections[key] = value
        print(f"\n## {key}\n{json.dumps(value, ensure_ascii=False, indent=2, default=str)}")


# ── auth ──────────────────────────────────────────────────────────────────────


async def cmd_auth() -> None:
    client = ClientAsync()

    def on_code(code: Any) -> None:
        print(f"\nОткройте {code.verification_url} и введите код:  {code.user_code}")
        print(f"(код действует {code.expires_in} с, опрос каждые {code.interval} с)\n")

    started = time.monotonic()
    token = await client.device_auth(on_code=on_code, device_name="Слушаем вместе (spike)")
    elapsed = time.monotonic() - started
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    lines = [line for line in lines if not line.startswith("YM_TOKEN=")]
    lines.append(f"YM_TOKEN={token.access_token}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"Готово за {elapsed:.0f} с. Токен записан в {ENV_FILE} (не печатается). "
        f"expires_in={token.expires_in}, refresh_token={'есть' if token.refresh_token else 'нет'}"
    )


# ── run ───────────────────────────────────────────────────────────────────────


async def probe_url(http: httpx.AsyncClient, url: str, ua: str = CHROME_UA) -> dict[str, Any]:
    """Range-запрос первых 64 КБ, как это сделал бы <audio>; плюс заголовки CORS/кеша."""
    headers = {
        "User-Agent": ua,
        "Range": "bytes=0-65535",
        "Origin": ORIGIN,
        "Referer": ORIGIN + "/",
    }
    t = time.monotonic()
    r = await http.get(url, headers=headers)
    h = r.headers
    return {
        "status": r.status_code,
        "ms": round((time.monotonic() - t) * 1000),
        "content_type": h.get("content-type"),
        "content_range": h.get("content-range"),
        "accept_ranges": h.get("accept-ranges"),
        "acao": h.get("access-control-allow-origin"),
        "cache_control": h.get("cache-control"),
        "expires": h.get("expires"),
        "sniff": sniff(r.content[:16]) if r.status_code in (200, 206) else None,
    }


async def probe_mid_range(http: httpx.AsyncClient, url: str) -> dict[str, Any]:
    r = await http.get(url, headers={"User-Agent": CHROME_UA, "Range": "bytes=2000000-2000999"})
    return {"status": r.status_code, "content_range": r.headers.get("content-range")}


def url_params(url: str) -> dict[str, list[str]]:
    q = parse_qs(urlparse(url).query)
    # Значения подписи прячем, оставляем только имена и «похожие на время» значения.
    out: dict[str, list[str]] = {}
    for k, v in q.items():
        out[k] = v if re.fullmatch(r"\d{9,13}", v[0] or "") else ["<redacted>"]
    return out


async def cmd_run(args: argparse.Namespace) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = Report()
    saved_urls: list[dict[str, Any]] = []

    client = await ClientAsync(load_token(), request=None).init()
    if kw := make_request_kwargs():
        client.request.proxy_url = kw["proxy_url"]

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as ip_http:
        try:
            ip = (await ip_http.get("https://ipinfo.io/json")).json()
            report.put("egress", {"country": ip.get("country"), "org": ip.get("org")})
        except httpx.HTTPError as e:
            report.put("egress", {"error": str(e)})

    # 1. Аккаунт
    st = client.me
    acc = st.account if st else None
    report.put(
        "account",
        {
            "uid": acc.uid if acc else None,
            "login": acc.login if acc else None,
            "display_name": acc.display_name if acc else None,
            "has_plus": st.plus.has_plus if st and st.plus else None,
            "subscription_end": (
                st.subscription.end
                if st and st.subscription and hasattr(st.subscription, "end")
                else None
            ),
            "avatar_hint": "https://avatars.yandex.net/get-yapic/{default_avatar_id}/islands-200",
        },
    )

    # 2. Поиск
    t = time.monotonic()
    sr = await client.search(args.query)
    report.put(
        "search",
        {
            "query": args.query,
            "ms": round((time.monotonic() - t) * 1000),
            "best_type": sr.best.type if sr.best else None,
            "totals": {
                k: getattr(sr, k).total if getattr(sr, k) else 0
                for k in ("tracks", "albums", "artists", "playlists", "videos", "podcasts")
            },
        },
    )
    track = sr.tracks.results[0]
    track_id = str(track.id)
    album_id = str(track.albums[0].id) if track.albums else None
    artist_id = str(track.artists[0].id) if track.artists else None

    report.put(
        "track_sample",
        {
            "id": track_id,
            "title": track.title,
            "artists": [a.name for a in track.artists],
            "duration_ms": track.duration_ms,
            "available": track.available,
            "available_for_premium_users": track.available_for_premium_users,
            "cover_uri": track.cover_uri,
            "cover_example_400": "https://" + (track.cover_uri or "").replace("%%", "400x400"),
            "og_image": track.og_image,
        },
    )

    # 3. Ссылки на аудио: старый метод download-info
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as http:
        legacy: list[dict[str, Any]] = []
        for d in await client.tracks_download_info(track_id):
            entry: dict[str, Any] = {
                "codec": d.codec,
                "bitrate": d.bitrate_in_kbps,
                "gain": d.gain,
                "preview": d.preview,
            }
            try:
                link = await d.get_direct_link_async()
                entry["url"] = redact_url(link)
                entry["params"] = url_params(link)
                entry["probe"] = await probe_url(http, link)
                entry["probe_other_ua"] = (await probe_url(http, link, OTHER_UA))["status"]
                entry["mid_range"] = await probe_mid_range(http, link)
                saved_urls.append({"kind": f"legacy-{d.codec}-{d.bitrate_in_kbps}", "url": link})
            except (YandexMusicError, httpx.HTTPError) as e:
                entry["error"] = f"{type(e).__name__}: {e}"
            legacy.append(entry)
        report.put("download_info_legacy", legacy)

        # 4. Новый метод get-file-info: качество × транспорт
        file_info: list[dict[str, Any]] = []
        codec_sets: dict[str, list[str] | None] = {
            "all": None,
            "browser_safe": ["mp3", "aac", "he-aac", "aac-mp4", "he-aac-mp4"],
            "flac_only": ["flac", "flac-mp4"],
        }
        for quality in ("lossless", "hq", "nq"):
            for transport in ("raw", "encraw"):
                for set_name, codecs in codec_sets.items():
                    if transport == "encraw" and set_name != "all":
                        continue
                    entry = {"quality": quality, "transport_req": transport, "codecs": set_name}
                    try:
                        fi = await client.tracks_file_info(track_id, quality, codecs, transport)
                        info = fi.download_info if fi else None
                        if info is None:
                            entry["result"] = None
                        else:
                            entry |= {
                                "codec": info.codec,
                                "bitrate": info.bitrate,
                                "transport": info.transport,
                                "has_key": bool(info.key),
                                "urls_count": len(info.urls),
                                "url": redact_url(info.url),
                                "params": url_params(info.url),
                                "probe": await probe_url(http, info.url),
                            }
                            if transport == "raw":
                                entry["probe_other_ua"] = (
                                    await probe_url(http, info.url, OTHER_UA)
                                )["status"]
                                entry["mid_range"] = await probe_mid_range(http, info.url)
                                saved_urls.append(
                                    {
                                        "kind": f"fileinfo-{quality}-{set_name}-{info.codec}",
                                        "url": info.url,
                                        "codec": info.codec,
                                    }
                                )
                    except (YandexMusicError, httpx.HTTPError) as e:
                        entry["error"] = f"{type(e).__name__}: {str(e)[:200]}"
                    file_info.append(entry)
        report.put("file_info", file_info)

    # 5. Метаданные
    meta: dict[str, Any] = {}
    if album_id:
        t = time.monotonic()
        album = await client.albums_with_tracks(album_id)
        vols = album.volumes or [] if album else []
        meta["album"] = {
            "id": album_id,
            "title": album.title if album else None,
            "ms": round((time.monotonic() - t) * 1000),
            "volumes": len(vols),
            "tracks": sum(len(v) for v in vols),
        }
    if artist_id:
        t = time.monotonic()
        info = await client.artists_brief_info(artist_id)
        top = await client.artists_tracks(artist_id, page_size=20)
        albums = await client.artists_direct_albums(artist_id, page_size=20)
        meta["artist"] = {
            "id": artist_id,
            "ms": round((time.monotonic() - t) * 1000),
            "brief_popular_tracks": len(info.popular_tracks or []) if info else None,
            "artists_tracks_page": len(top.tracks) if top else None,
            "artists_tracks_total": top.pager.total if top and top.pager else None,
            "direct_albums": len(albums.albums) if albums else None,
        }

    uid = client.me.account.uid if client.me and client.me.account else None
    t = time.monotonic()
    my_lists = await client.users_playlists_list()
    meta["my_playlists"] = {
        "ms": round((time.monotonic() - t) * 1000),
        "count": len(my_lists),
        "sample": [
            {
                "kind": p.kind,
                "title": p.title,
                "track_count": p.track_count,
                "uuid": p.playlist_uuid,
                "owner": p.owner.login if p.owner else None,
            }
            for p in my_lists[:5]
        ],
    }
    t = time.monotonic()
    likes = await client.users_likes_tracks()
    meta["liked"] = {
        "ms": round((time.monotonic() - t) * 1000),
        "count": len(likes) if likes else 0,
        "note": "users_likes_tracks возвращает TrackShort; полные треки — fetch_tracks_async / tracks(ids)",
    }
    if likes and len(likes) > 0:
        t = time.monotonic()
        full = await client.tracks([ts.track_id for ts in likes.tracks[:100]])
        meta["liked"]["fetch_100_full_ms"] = round((time.monotonic() - t) * 1000)
        meta["liked"]["fetched"] = len(full)

    t = time.monotonic()
    liked_albums = await client.users_likes_albums()
    meta["liked_albums"] = {
        "ms": round((time.monotonic() - t) * 1000),
        "count": len(liked_albums or []),
    }

    # Плейлист по owner/kind и по UUID (одному и тому же)
    if my_lists:
        p0 = my_lists[0]
        t = time.monotonic()
        by_kind = await client.users_playlists(p0.kind, uid)
        meta["playlist_by_kind"] = {
            "ms": round((time.monotonic() - t) * 1000),
            "tracks": len(by_kind.tracks or []) if by_kind else None,
        }
        if p0.playlist_uuid:
            t = time.monotonic()
            by_uuid = await client.playlist(p0.playlist_uuid)
            meta["playlist_by_uuid"] = {
                "ms": round((time.monotonic() - t) * 1000),
                "uuid": p0.playlist_uuid,
                "tracks": len(by_uuid.tracks or []) if by_uuid else None,
                "kind_matches": by_uuid.kind == p0.kind if by_uuid else None,
            }
    if sr.playlists and sr.playlists.results:
        pub = sr.playlists.results[0]
        if pub.playlist_uuid:
            t = time.monotonic()
            by_uuid = await client.playlist(pub.playlist_uuid)
            meta["public_playlist_by_uuid"] = {
                "ms": round((time.monotonic() - t) * 1000),
                "uuid": pub.playlist_uuid,
                "owner": pub.owner.login if pub.owner else None,
                "kind": pub.kind,
                "tracks": len(by_uuid.tracks or []) if by_uuid else None,
            }
    report.put("metadata", meta)

    (OUT / "urls.json").write_text(
        json.dumps({"fetched_at": time.time(), "urls": saved_urls}, indent=2), encoding="utf-8"
    )
    (OUT / "report.json").write_text(
        json.dumps(report.sections, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"\nОтчёт: {OUT / 'report.json'}; ссылки для recheck/браузера: {OUT / 'urls.json'}")


# ── recheck ───────────────────────────────────────────────────────────────────


async def cmd_recheck() -> None:
    data = json.loads((OUT / "urls.json").read_text(encoding="utf-8"))
    age = time.time() - data["fetched_at"]
    print(f"Ссылкам {age / 60:.1f} мин")
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as http:
        for item in data["urls"]:
            p = await probe_url(http, item["url"])
            print(f"  {item['kind']:<45} status={p['status']} sniff={p['sniff']}")
    history = OUT / "recheck.log"
    with history.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} age_min={age / 60:.1f}\n")


# ── links ─────────────────────────────────────────────────────────────────────


async def cmd_links(urls: list[str]) -> None:
    """Разворачивает короткие ссылки и показывает итоговый URL — для каталога форматов."""
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as http:
        for url in urls:
            try:
                r = await http.get(url, headers={"User-Agent": CHROME_UA})
                chain = [str(h.url) for h in r.history] + [str(r.url)]
                print(f"{url}\n   → {' → '.join(chain)}  [{r.status_code}]")
            except httpx.HTTPError as e:
                print(f"{url}\n   ! {e}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # Windows-консоль
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth")
    run = sub.add_parser("run")
    run.add_argument("--query", default="Radiohead Creep")
    sub.add_parser("recheck")
    links = sub.add_parser("links")
    links.add_argument("urls", nargs="+")
    args = parser.parse_args()

    match args.cmd:
        case "auth":
            asyncio.run(cmd_auth())
        case "run":
            asyncio.run(cmd_run(args))
        case "recheck":
            asyncio.run(cmd_recheck())
        case "links":
            asyncio.run(cmd_links(args.urls))


if __name__ == "__main__":
    main()
