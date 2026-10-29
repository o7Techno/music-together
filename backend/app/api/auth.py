"""Аутентификация: конфиг входа, dev-логин, профиль, выход (Device Flow — в yandex_auth.py)."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Request, Response

from app.api.deps import Ctx, CurrentUser, Db, current_user, set_session_cookie
from app.api.schemas import AuthConfig, DevLoginRequest, Me, SessionInfo
from app.auth.sessions import COOKIE_NAME, create_session, delete_session
from app.core.config import MusicProviderKind
from app.core.errors import ForbiddenError, UnauthorizedError
from app.db.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/config")
async def auth_config(ctx: Ctx) -> AuthConfig:
    return AuthConfig(
        dev_login=ctx.settings.allow_dev_login,
        yandex_login=ctx.settings.music_provider is MusicProviderKind.YANDEX,
    )


@router.post("/dev-login")
async def dev_login(body: DevLoginRequest, response: Response, ctx: Ctx, db: Db) -> Me:
    """Вход без Яндекса (разработка, e2e, демо на FakeProvider). Каждый вход — новый юзер."""
    if not ctx.settings.allow_dev_login:
        raise ForbiddenError("Вход без Яндекса отключён.")
    name = body.name.strip()
    user = User(
        provider="dev",
        external_id=secrets.token_hex(8),
        login=name,
        display_name=name,
        has_plus=True,
    )
    db.add(user)
    await db.commit()
    raw, _ = await create_session(db, user, ctx.settings.session_secret.get_secret_value())
    set_session_cookie(response, ctx.settings, raw)
    return Me.of(user)


@router.get("/me")
async def me(user: CurrentUser) -> Me:
    return Me.of(user)


@router.get("/session")
async def session(request: Request, response: Response, ctx: Ctx, db: Db) -> SessionInfo:
    """Кто вошёл — без 401 для анонимов (главная страница не шумит ошибками в консоли)."""
    try:
        user = await current_user(request, response, ctx, db)
    except UnauthorizedError:
        return SessionInfo(me=None)
    return SessionInfo(me=Me.of(user))


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, ctx: Ctx, db: Db) -> None:
    raw = request.cookies.get(COOKIE_NAME)
    if raw:
        await delete_session(db, raw, ctx.settings.session_secret.get_secret_value())
    response.delete_cookie(COOKIE_NAME, path="/")
