"""Получение аудио (SPEC §6.2): `direct` — ссылка только этому пользователю; `proxy` — поток через
бэкенд с поддержкой Range, без записи на диск и без общего кеша между пользователями."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.deps import Ctx, CurrentUser, Provider, limit
from app.core.config import AudioMode
from app.core.errors import RateLimitedError
from app.providers.base import ProviderError, StreamInfo, StreamMode

router = APIRouter(prefix="/api/stream", tags=["stream"])

MAX_STREAMS_PER_USER = 4
UPSTREAM_LINK_TTL_S = 10 * 60
CHUNK = 64 * 1024
_CONTENT_TYPES = {
    "mp3": "audio/mpeg",
    "aac": "audio/aac",
    "he-aac": "audio/aac",
    "aac-mp4": "audio/mp4",
    "he-aac-mp4": "audio/mp4",
}
_PASS_HEADERS = ("content-length", "content-range", "accept-ranges", "last-modified", "etag")

_active: defaultdict[str, int] = defaultdict(int)
# Ссылка на апстрим для конкретного пользователя и трека: браузер шлёт серию Range-запросов при
# перемотке, и без этого каждый запрос стоил бы обращения к API Яндекса. Это не кеш аудио и не
# общий кеш — запись видна только этому пользователю и живёт минуты (DECISIONS D-025).
_links: dict[tuple[str, str], tuple[float, StreamInfo]] = {}


@router.get("/{track_id}", dependencies=[limit("stream_limiter")])
async def stream_info(track_id: str, provider: Provider, ctx: Ctx) -> StreamInfo:
    """Как играть трек: прямая ссылка (direct) или URL прокси-потока (proxy)."""
    info = await provider.get_stream(track_id)
    if ctx.settings.audio_mode is AudioMode.PROXY and info.url.startswith("http"):
        return StreamInfo(
            track_id=track_id,
            mode=StreamMode.PROXY,
            url=f"/api/stream/{track_id}/audio",
            codec=info.codec,
            bitrate=info.bitrate,
        )
    return info


async def _upstream(user_id: str, track_id: str, provider: Provider, *, fresh: bool) -> StreamInfo:
    key = (user_id, track_id)
    cached = _links.get(key)
    now = time.monotonic()
    if cached and not fresh and now - cached[0] < UPSTREAM_LINK_TTL_S:
        return cached[1]
    info = await provider.get_stream(track_id)
    _links[key] = (now, info)
    for k in [k for k, (at, _) in _links.items() if now - at > UPSTREAM_LINK_TTL_S]:
        del _links[k]
    return info


@router.get("/{track_id}/audio")
async def stream_audio(
    track_id: str, request: Request, user: CurrentUser, provider: Provider, ctx: Ctx
) -> StreamingResponse:
    if ctx.settings.audio_mode is not AudioMode.PROXY:
        raise ProviderError("Прокси-режим аудио выключен на сервере.")
    if _active[user.id] >= MAX_STREAMS_PER_USER:
        raise RateLimitedError("Слишком много одновременных потоков.")
    headers = {"User-Agent": "Mozilla/5.0"}
    if rng := request.headers.get("range"):
        headers["Range"] = rng

    client = httpx.AsyncClient(timeout=httpx.Timeout(15, read=30), proxy=ctx.settings.ym_proxy_url)
    upstream: httpx.Response | None = None
    for fresh in (False, True):
        info = await _upstream(user.id, track_id, provider, fresh=fresh)
        req = client.build_request("GET", info.url, headers=headers)
        upstream = await client.send(req, stream=True)
        if upstream.status_code in (200, 206):
            break
        await upstream.aclose()  # ссылка протухла — берём свежую
    if upstream is None or upstream.status_code not in (200, 206):
        await client.aclose()
        raise ProviderError("Не удалось получить аудио от Яндекса.")

    response_headers = {k: v for k in _PASS_HEADERS if (v := upstream.headers.get(k))}
    response_headers["Accept-Ranges"] = "bytes"
    response_headers["Cache-Control"] = "no-store"
    _active[user.id] += 1
    resp = upstream

    async def body() -> AsyncIterator[bytes]:
        try:
            async for chunk in resp.aiter_bytes(CHUNK):
                yield chunk
        except (httpx.HTTPError, asyncio.CancelledError):
            return
        finally:
            _active[user.id] -= 1
            await resp.aclose()
            await client.aclose()

    return StreamingResponse(
        body(),
        status_code=resp.status_code,
        headers=response_headers,
        media_type=_CONTENT_TYPES.get(info.codec, "application/octet-stream"),
    )
