"""Музыкальные REST-роуты. Всё идёт через провайдер текущего пользователя — его токеном."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import Field

from app.api.deps import Provider, limit
from app.core.errors import ValidationError
from app.core.schema import ApiModel
from app.providers.base import (
    AlbumSummary,
    PlaylistSummary,
    ProviderError,
    SearchResult,
    TrackList,
)
from app.providers.yandex_links import extract_links

router = APIRouter(prefix="/api", tags=["music"])


@router.get("/search", dependencies=[limit("search_limiter")])
async def search(
    provider: Provider, q: Annotated[str, Query(min_length=1, max_length=200)]
) -> SearchResult:
    return await provider.search(q)


@router.get("/albums/{album_id}")
async def album(album_id: str, provider: Provider) -> TrackList:
    return await provider.get_album(album_id)


@router.get("/playlists/{ref}")
async def playlist(ref: str, provider: Provider) -> TrackList:
    return await provider.get_playlist(ref)


@router.get("/artists/{artist_id}")
async def artist(artist_id: str, provider: Provider) -> TrackList:
    return await provider.get_artist(artist_id)


@router.get("/me/playlists")
async def my_playlists(provider: Provider) -> list[PlaylistSummary]:
    return await provider.get_user_playlists()


@router.get("/me/liked")
async def my_liked(provider: Provider) -> TrackList:
    return await provider.get_liked_tracks()


@router.get("/me/albums")
async def my_albums(provider: Provider) -> list[AlbumSummary]:
    return await provider.get_liked_albums()


class ResolveRequest(ApiModel):
    text: str = Field(min_length=1, max_length=20_000)
    """Одна или несколько ссылок (по одной на строку или вперемешку с текстом)."""


class ResolveFailure(ApiModel):
    kind: str
    id: str
    message: str


class ResolveResponse(ApiModel):
    items: list[TrackList]
    failures: list[ResolveFailure]


MAX_LINKS = 20


@router.post("/resolve-link", dependencies=[limit("search_limiter")])
async def resolve_link(body: ResolveRequest, provider: Provider) -> ResolveResponse:
    """Понять, на что ссылки (трек/альбом/плейлист/артист), и вернуть их треки."""
    links = extract_links(body.text, limit=MAX_LINKS)
    if not links:
        raise ValidationError("Не нашли ссылок Яндекс Музыки — проверьте, что ссылка полная.")
    items: list[TrackList] = []
    failures: list[ResolveFailure] = []
    for link in links:
        try:
            items.append(await provider.resolve(link))
        except ProviderError as e:
            failures.append(ResolveFailure(kind=link.kind.value, id=link.id, message=e.message))
    return ResolveResponse(items=items, failures=failures)
