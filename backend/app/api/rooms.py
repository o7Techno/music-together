"""REST комнат: создание, «Мои комнаты», права создателя (SPEC §4.2)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Ctx, CurrentUser, Db
from app.api.schemas import (
    CreateRoomRequest,
    RoomDetails,
    RoomSummary,
    SlugResponse,
    UpdateRoomRequest,
)
from app.rooms import service
from app.rooms.room import RoomUser
from app.ws.protocol import CloseReason

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


def _online(ctx: Ctx, room_id: str) -> int:
    room = ctx.rooms.loaded(room_id)
    return len({c.user.id for c in room.clients.values()}) if room else 0


@router.post("", status_code=201)
async def create_room(body: CreateRoomRequest, user: CurrentUser, db: Db) -> RoomSummary:
    name = body.name.strip() if body.name else None
    room = await service.create_room(db, user, name or None)
    return RoomSummary(slug=room.slug, name=room.name, is_owner=True)


@router.get("")
async def my_rooms(user: CurrentUser, db: Db, ctx: Ctx) -> list[RoomSummary]:
    rooms = await service.list_my_rooms(db, user)
    result: list[RoomSummary] = []
    for r in rooms:
        record = await service.get_room_by_slug(db, r.slug)
        result.append(
            RoomSummary(
                slug=r.slug,
                name=r.name,
                is_owner=r.is_owner,
                last_joined_at=r.last_joined_at,
                online=_online(ctx, record.id),
            )
        )
    return result


@router.get("/{slug}")
async def room_details(slug: str, user: CurrentUser, db: Db) -> RoomDetails:
    room = await service.get_room_by_slug(db, slug)
    return RoomDetails(
        id=room.id,
        slug=room.slug,
        name=room.name,
        owner_id=room.owner_id,
        is_owner=room.owner_id == user.id,
    )


@router.patch("/{slug}")
async def update_room(
    slug: str, body: UpdateRoomRequest, user: CurrentUser, db: Db, ctx: Ctx
) -> RoomDetails:
    room = await service.get_room_by_slug(db, slug)
    service.ensure_owner(room, user)
    name = body.name.strip() if body.name else None
    if name:
        await service.rename_room(db, room, name)
    # Настройки живут в живой комнате и сохраняются вместе с её состоянием.
    live = await ctx.rooms.get(room)
    async with live.lock:
        if name:
            live.rename(name, RoomUser(id=user.id, name=user.display_name))
        changes = body.model_dump(exclude={"name"}, exclude_none=True, by_alias=False)
        if changes:
            live.update_settings(live.settings.model_copy(update=changes))
    return RoomDetails(
        id=room.id, slug=room.slug, name=room.name, owner_id=room.owner_id, is_owner=True
    )


@router.delete("/{slug}", status_code=204)
async def delete_room(slug: str, user: CurrentUser, db: Db, ctx: Ctx) -> None:
    room = await service.get_room_by_slug(db, slug)
    service.ensure_owner(room, user)
    room_id = room.id
    await service.delete_room(db, room)
    await ctx.rooms.drop(room_id, CloseReason.DELETED)


@router.post("/{slug}/reissue")
async def reissue_link(slug: str, user: CurrentUser, db: Db, ctx: Ctx) -> SlugResponse:
    """Перевыпустить ссылку-приглашение: старая перестаёт работать, подключённые остаются."""
    room = await service.get_room_by_slug(db, slug)
    service.ensure_owner(room, user)
    new_slug = await service.reissue_slug(db, room)
    live = ctx.rooms.loaded(room.id)
    if live is not None:
        async with live.lock:
            live.set_slug(new_slug)
    return SlugResponse(slug=new_slug)


@router.post("/{slug}/kick/{user_id}", status_code=204)
async def kick_member(slug: str, user_id: str, user: CurrentUser, db: Db, ctx: Ctx) -> None:
    room = await service.get_room_by_slug(db, slug)
    service.ensure_owner(room, user)
    await service.ban_member(db, room, user_id)
    live = ctx.rooms.loaded(room.id)
    if live is not None:
        async with live.lock:
            live.kick(user_id, RoomUser(id=user.id, name=user.display_name))
