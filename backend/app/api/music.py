"""Музыкальные REST-роуты. Всё идёт через провайдер текущего пользователя — его токеном."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import Provider, limit
from app.providers.base import AlbumSummary, PlaylistSummary, SearchResult, StreamInfo, TrackList

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


@router.get("/stream/{track_id}", dependencies=[limit("stream_limiter")])
async def stream(track_id: str, provider: Provider) -> StreamInfo:
    """Ссылка на аудио — только для запросившего пользователя, получена его токеном.

    Ответ не кешируется ни на сервере, ни в браузере (заголовок ставит middleware для /api/stream).
    """
    return await provider.get_stream(track_id)
