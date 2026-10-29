"""Вход через Яндекс (SPEC §4.1): Device Flow и запасной вход по токену."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import Field

from app.api.deps import Ctx, Db, set_session_cookie
from app.api.schemas import Me
from app.auth.crypto import TokenCipher
from app.auth.sessions import create_session
from app.auth.yandex_login import upsert_yandex_user
from app.auth.yandex_oauth import DeviceFlowError, TokenData, YandexAuth
from app.core.context import AppContext
from app.core.errors import ForbiddenError, RateLimitedError
from app.core.schema import ApiModel

router = APIRouter(prefix="/api/auth", tags=["auth"])


class DeviceStartResponse(ApiModel):
    flow_id: str
    user_code: str
    verification_url: str
    expires_in: int
    interval: int


class DevicePollRequest(ApiModel):
    flow_id: str = Field(min_length=10, max_length=64)


class DevicePollResponse(ApiModel):
    status: Literal["pending", "ok", "expired"]
    me: Me | None = None


class TokenLoginRequest(ApiModel):
    token: str = Field(min_length=20, max_length=512)


def _auth(ctx: AppContext) -> tuple[YandexAuth, TokenCipher]:
    if ctx.yandex_auth is None or ctx.cipher is None:
        raise ForbiddenError("Вход через Яндекс не настроен на этом сервере.")
    return ctx.yandex_auth, ctx.cipher


def _limit(ctx: AppContext, request: Request) -> None:
    key = request.client.host if request.client else "unknown"
    if not ctx.login_limiter.allow(key):
        raise RateLimitedError


async def _login(ctx: AppContext, db: Db, response: Response, token: TokenData) -> Me:
    auth, cipher = _auth(ctx)
    profile = await auth.profile(token.access_token)
    user = await upsert_yandex_user(db, cipher, profile, token)
    raw, _ = await create_session(db, user, ctx.settings.session_secret.get_secret_value())
    set_session_cookie(response, ctx.settings, raw)
    return Me.of(user)


@router.post("/device/start")
async def device_start(ctx: Ctx, request: Request) -> DeviceStartResponse:
    """Код для ya.ru/device. `device_code` остаётся на сервере, клиенту — только flow_id."""
    _limit(ctx, request)
    code = await _auth(ctx)[0].request_device_code()
    flow_id = ctx.device_flows.add(code)
    return DeviceStartResponse(
        flow_id=flow_id,
        user_code=code.user_code,
        verification_url=code.verification_url,
        expires_in=code.expires_in,
        interval=code.interval,
    )


@router.post("/device/poll")
async def device_poll(
    body: DevicePollRequest, response: Response, ctx: Ctx, db: Db
) -> DevicePollResponse:
    flow = ctx.device_flows.get(body.flow_id)
    if flow is None:
        return DevicePollResponse(status="expired")
    if ctx.device_flows.too_early(flow):
        return DevicePollResponse(status="pending")
    try:
        token = await _auth(ctx)[0].poll_device_token(flow.device_code)
    except DeviceFlowError:
        ctx.device_flows.remove(body.flow_id)
        return DevicePollResponse(status="expired")
    if token is None:
        return DevicePollResponse(status="pending")
    ctx.device_flows.remove(body.flow_id)
    return DevicePollResponse(status="ok", me=await _login(ctx, db, response, token))


@router.post("/token-login")
async def token_login(
    body: TokenLoginRequest, request: Request, response: Response, ctx: Ctx, db: Db
) -> Me:
    """Запасной вход: пользователь вставляет OAuth-токен Яндекс Музыки вручную."""
    _limit(ctx, request)
    token = TokenData(access_token=body.token.strip(), refresh_token=None, expires_in=None)
    return await _login(ctx, db, response, token)
