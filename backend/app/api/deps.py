"""Зависимости FastAPI: контекст, сессия БД, текущий пользователь, rate limit."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request, Response, params
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.sessions import COOKIE_NAME, SESSION_TTL, resolve_session
from app.core.config import Settings
from app.core.context import AppContext
from app.core.errors import RateLimitedError, UnauthorizedError
from app.core.ratelimit import RateLimiter
from app.db.models import User
from app.providers.base import MusicProvider


def get_ctx(request: Request) -> AppContext:
    ctx: AppContext = request.app.state.ctx
    return ctx


Ctx = Annotated[AppContext, Depends(get_ctx)]


async def get_db(ctx: Ctx) -> AsyncIterator[AsyncSession]:
    async with ctx.db.sessionmaker() as session:
        yield session


Db = Annotated[AsyncSession, Depends(get_db)]


def set_session_cookie(response: Response, settings: Settings, raw_token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        raw_token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


async def current_user(request: Request, response: Response, ctx: Ctx, db: Db) -> User:
    raw = request.cookies.get(COOKIE_NAME, "")
    resolved = await resolve_session(db, raw, ctx.settings.session_secret.get_secret_value())
    if resolved is None:
        raise UnauthorizedError
    user, renewed = resolved
    if renewed is not None:
        set_session_cookie(response, ctx.settings, raw)
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def provider_for(ctx: Ctx, user: CurrentUser) -> MusicProvider:
    return ctx.providers.for_user(user)


Provider = Annotated[MusicProvider, Depends(provider_for)]


def limit(limiter_attr: str) -> params.Depends:
    def check(ctx: Ctx, user: CurrentUser) -> None:
        limiter: RateLimiter = getattr(ctx, limiter_attr)
        if not limiter.allow(user.id):
            raise RateLimitedError

    dependency: params.Depends = Depends(check)
    return dependency
