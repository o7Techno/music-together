"""Личная коллекция: лайки, плейлисты, настройки волны. Всё действует на аккаунт того, кто нажал."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import Field

from app.api.deps import Ctx, CurrentUser, Db, Provider, limit
from app.api.schemas import Me
from app.core.errors import NotFoundError
from app.core.schema import ApiModel
from app.db.models import RoomMember
from app.providers.base import PlaylistSummary, WaveOptions
from app.rooms import service
from app.rooms.room import RoomUser
from app.ws.protocol import MAX_BATCH_TRACKS

router = APIRouter(
    prefix="/api/me", tags=["collection"], dependencies=[limit("collection_limiter")]
)

RoomSlug = Annotated[str | None, Query(alias="room", max_length=64)]


class LikedIds(ApiModel):
    track_ids: list[str]


class CreatePlaylistRequest(ApiModel):
    title: str = Field(min_length=1, max_length=100)


class AddToPlaylistRequest(ApiModel):
    track_ids: list[str] = Field(min_length=1, max_length=MAX_BATCH_TRACKS)
    allow_duplicate: bool = False


class UserSettingsRequest(ApiModel):
    wave_learning: bool


async def _note_like(
    ctx: Ctx, db: Db, user: CurrentUser, *, slug: str | None, track_id: str, liked: bool
) -> None:
    """Лайк из комнаты: событие в ленту, счётчик на текущем треке, фидбек своей волны."""
    if slug is None:
        return
    try:
        record = await service.get_room_by_slug(db, slug)
    except NotFoundError:
        return
    member = await db.get(RoomMember, (record.id, user.id))
    live = ctx.rooms.loaded(record.id)
    if live is None or member is None or member.banned:
        return
    room_user = RoomUser(id=user.id, name=user.display_name, avatar_url=user.avatar_url)
    await live.note_like(room_user, track_id, liked=liked)


@router.get("/liked/ids")
async def liked_ids(provider: Provider) -> LikedIds:
    return LikedIds(track_ids=sorted(await provider.get_liked_track_ids()))


@router.put("/liked/{track_id}", status_code=204)
async def like(
    track_id: str, *, provider: Provider, ctx: Ctx, db: Db, user: CurrentUser, slug: RoomSlug = None
) -> None:
    await provider.like_track(track_id)
    await _note_like(ctx, db, user, slug=slug, track_id=track_id, liked=True)


@router.delete("/liked/{track_id}", status_code=204)
async def unlike(
    track_id: str, *, provider: Provider, ctx: Ctx, db: Db, user: CurrentUser, slug: RoomSlug = None
) -> None:
    await provider.unlike_track(track_id)
    await _note_like(ctx, db, user, slug=slug, track_id=track_id, liked=False)


@router.post("/playlists", status_code=201)
async def create_playlist(body: CreatePlaylistRequest, provider: Provider) -> PlaylistSummary:
    return await provider.create_playlist(body.title.strip())


@router.post("/playlists/{ref}/tracks")
async def add_to_playlist(
    ref: str, body: AddToPlaylistRequest, provider: Provider
) -> PlaylistSummary:
    return await provider.add_to_playlist(ref, body.track_ids, allow_duplicate=body.allow_duplicate)


@router.delete("/playlists/{ref}/tracks/{track_id}")
async def remove_from_playlist(ref: str, track_id: str, provider: Provider) -> PlaylistSummary:
    return await provider.remove_from_playlist(ref, track_id)


@router.get("/wave/options")
async def wave_options(provider: Provider) -> WaveOptions:
    return await provider.get_wave_options()


@router.patch("/settings")
async def update_settings(body: UserSettingsRequest, user: CurrentUser, db: Db) -> Me:
    stored = await db.merge(user)
    stored.wave_learning = body.wave_learning
    await db.commit()
    return Me.of(stored)
