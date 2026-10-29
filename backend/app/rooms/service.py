"""Операции с комнатами в БД: создание, «мои комнаты», участники, права создателя."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError
from app.db.models import Room, RoomMember, User, utcnow

# Без похожих символов (0/o, 1/l/i): ссылку можно продиктовать.
_SLUG_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_SLUG_HALF = 5


def generate_slug() -> str:
    """`xxxxx-xxxxx`: 31^10 ≈ 8·10^14 вариантов — неугадываемо, но читается и диктуется."""
    halves = ("".join(secrets.choice(_SLUG_ALPHABET) for _ in range(_SLUG_HALF)) for _ in "ab")
    return "-".join(halves)


def default_room_name(user: User) -> str:
    return f"Комната {user.display_name}"[:80]


async def create_room(db: AsyncSession, owner: User, name: str | None) -> Room:
    for _ in range(5):
        room = Room(
            slug=generate_slug(), name=(name or default_room_name(owner))[:80], owner_id=owner.id
        )
        db.add(room)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            continue
        db.add(RoomMember(room_id=room.id, user_id=owner.id))
        await db.commit()
        return room
    raise RuntimeError("не удалось сгенерировать уникальный slug")


async def get_room_by_slug(db: AsyncSession, slug: str) -> Room:
    room = (await db.execute(select(Room).where(Room.slug == slug))).scalar_one_or_none()
    if room is None:
        raise NotFoundError(
            "Комната не найдена — возможно, ссылку перевыпустили или комнату удалили."
        )
    return room


async def touch_membership(db: AsyncSession, room: Room, user: User) -> None:
    """Отметить вход в комнату. Выгнанным вход закрыт."""
    member = await db.get(RoomMember, (room.id, user.id))
    if member is None:
        db.add(RoomMember(room_id=room.id, user_id=user.id))
    elif member.banned:
        raise ForbiddenError("Создатель комнаты закрыл вам доступ.")
    else:
        member.last_joined_at = utcnow()
    await db.commit()


@dataclass
class MyRoom:
    slug: str
    name: str
    is_owner: bool
    last_joined_at: datetime


async def list_my_rooms(db: AsyncSession, user: User, limit: int = 30) -> list[MyRoom]:
    rows = await db.execute(
        select(RoomMember)
        .where(RoomMember.user_id == user.id, RoomMember.banned.is_(False))
        .order_by(RoomMember.last_joined_at.desc())
        .limit(limit)
    )
    return [
        MyRoom(
            slug=m.room.slug,
            name=m.room.name,
            is_owner=m.room.owner_id == user.id,
            last_joined_at=m.last_joined_at,
        )
        for m in rows.scalars()
    ]


def ensure_owner(room: Room, user: User) -> None:
    if room.owner_id != user.id:
        raise ForbiddenError("Это может только создатель комнаты.")


async def rename_room(db: AsyncSession, room: Room, name: str) -> None:
    room.name = name[:80]
    await db.commit()


async def reissue_slug(db: AsyncSession, room: Room) -> str:
    for _ in range(5):
        room.slug = generate_slug()
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            continue
        return room.slug
    raise RuntimeError("не удалось сгенерировать уникальный slug")


async def ban_member(db: AsyncSession, room: Room, user_id: str) -> None:
    if user_id == room.owner_id:
        raise ForbiddenError("Нельзя выгнать создателя комнаты.")
    member = await db.get(RoomMember, (room.id, user_id))
    if member is None:
        db.add(RoomMember(room_id=room.id, user_id=user_id, banned=True))
    else:
        member.banned = True
    await db.commit()


async def delete_room(db: AsyncSession, room: Room) -> None:
    await db.delete(room)
    await db.commit()
