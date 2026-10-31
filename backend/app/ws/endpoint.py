"""WebSocket комнаты `/ws/rooms/{slug}` (SPEC §7.4).

Проверки до работы: Origin, сессионная cookie, существование комнаты, бан. Дальше — цикл чтения:
пинги обслуживаются сразу (минимальная задержка для синхронизации часов), остальное — через актор.
"""

from __future__ import annotations

import secrets

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError as PydanticValidationError

from app.auth.sessions import COOKIE_NAME, resolve_session
from app.core.context import AppContext
from app.core.errors import AppError, ForbiddenError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import User
from app.providers.base import Track, TrackUnavailableError
from app.rooms import service
from app.rooms.room import Room, RoomUser
from app.ws.protocol import (
    MAX_MESSAGE_BYTES,
    WS_CLOSE_FORBIDDEN,
    WS_CLOSE_NOT_FOUND,
    WS_CLOSE_UNAUTHORIZED,
    ClientStatus,
    DriftReport,
    ErrorMessage,
    Ping,
    Pong,
    QueueAdd,
    Ready,
    client_message_adapter,
)

router = APIRouter()
log = get_logger(__name__)


async def _authenticate(ws: WebSocket, ctx: AppContext, slug: str) -> tuple[User, Room] | int:
    origin = ws.headers.get("origin")
    if origin not in ctx.settings.allowed_origins:
        return WS_CLOSE_FORBIDDEN
    async with ctx.db.sessionmaker() as db:
        raw = ws.cookies.get(COOKIE_NAME, "")
        resolved = await resolve_session(db, raw, ctx.settings.session_secret.get_secret_value())
        if resolved is None:
            return WS_CLOSE_UNAUTHORIZED
        user = resolved[0]
        try:
            record = await service.get_room_by_slug(db, slug)
            await service.touch_membership(db, record, user)
        except NotFoundError:
            return WS_CLOSE_NOT_FOUND
        except ForbiddenError:
            return WS_CLOSE_FORBIDDEN
        room = await ctx.rooms.get(record)
    return user, room


async def _resolve_tracks(ctx: AppContext, user: User, msg: QueueAdd) -> list[Track]:
    """Получить треки провайдером добавляющего и проверить их доступность у него (SPEC §4.4)."""
    provider = ctx.providers.for_user(user)
    tracks = await provider.get_tracks(msg.track_ids)
    by_id = {t.id: t for t in tracks}
    ordered = [by_id[i] for i in msg.track_ids if i in by_id]
    available = [t for t in ordered if t.available]
    if not available:
        raise TrackUnavailableError(
            "Трек недоступен для вашего аккаунта."
            if len(msg.track_ids) == 1
            else "Ни один из треков недоступен для вашего аккаунта."
        )
    return available


@router.websocket("/ws/rooms/{slug}")
async def room_socket(ws: WebSocket, slug: str) -> None:
    ctx: AppContext = ws.app.state.ctx
    await ws.accept()
    auth = await _authenticate(ws, ctx, slug)
    if isinstance(auth, int):
        await ws.close(code=auth)
        return
    user, room = auth
    conn_id = secrets.token_urlsafe(8)
    structlog.contextvars.bind_contextvars(room=room.slug, conn_id=conn_id, user_id=user.id)
    ctx.hub.register(conn_id, ws)
    room_user = RoomUser(
        id=user.id,
        name=user.display_name,
        avatar_url=user.avatar_url,
        can_wave=user.has_plus,
    )
    await room.join(conn_id, room_user)
    log.info("ws_connected")
    try:
        while True:
            raw = await ws.receive_text()
            if len(raw) > MAX_MESSAGE_BYTES:
                ctx.hub.send(
                    conn_id, ErrorMessage(code="too_large", message="Слишком большое сообщение.")
                )
                continue
            await _dispatch(ctx, room, conn_id, user, raw)
    except WebSocketDisconnect:
        pass
    finally:
        await room.leave(conn_id)
        await ctx.hub.unregister(conn_id)
        log.info("ws_disconnected")
        structlog.contextvars.clear_contextvars()


async def _dispatch(ctx: AppContext, room: Room, conn_id: str, user: User, raw: str) -> None:
    received_at = ctx.clock.now_ms()
    try:
        msg = client_message_adapter.validate_json(raw)
    except PydanticValidationError:
        ctx.hub.send(conn_id, ErrorMessage(code="bad_message", message="Некорректное сообщение."))
        return
    client_msg_id = getattr(msg, "client_msg_id", None)
    try:
        match msg:
            case Ping(t0=t0):
                ctx.hub.send(conn_id, Pong(t0=t0, server_time=received_at))
            case Ready():
                await room.ready(conn_id, msg)
            case ClientStatus():
                await room.update_client_status(conn_id, msg)
            case DriftReport():
                await room.report_drift(conn_id, msg)
            case QueueAdd():
                tracks = await _resolve_tracks(ctx, user, msg)
                await room.add_tracks(
                    conn_id,
                    msg.client_msg_id,
                    tracks,
                    position=msg.position,
                    index=msg.index,
                    source=msg.source,
                )
            case _:
                await room.handle(conn_id, msg)
    except AppError as e:
        ctx.hub.send(
            conn_id, ErrorMessage(client_msg_id=client_msg_id, code=e.code, message=e.message)
        )
    except ValueError as e:  # pragma: no cover — защитная сетка
        log.warning("ws_value_error", error=str(e))
        err = ValidationError()
        ctx.hub.send(
            conn_id, ErrorMessage(client_msg_id=client_msg_id, code=err.code, message=err.message)
        )
