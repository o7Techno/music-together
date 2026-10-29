"""Точка входа FastAPI-приложения."""

from __future__ import annotations

import asyncio
import contextlib
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.music import router as music_router
from app.api.rooms import router as rooms_router
from app.auth.crypto import TokenCipher
from app.core.clock import Clock, SystemClock
from app.core.config import Settings, get_settings
from app.core.context import AppContext
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger
from app.core.ratelimit import RateLimiter
from app.db.session import Database
from app.providers.factory import ProviderFactory, YandexProviderBuilder
from app.providers.fake import FAKE_MEDIA_DIR, FAKE_MEDIA_URL
from app.rooms.manager import RoomManager
from app.rooms.timers import AsyncioTimers
from app.ws.endpoint import router as ws_router
from app.ws.hub import ConnectionHub

log = get_logger(__name__)

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def build_context(settings: Settings, clock: Clock | None = None) -> AppContext:
    clock = clock or SystemClock()
    db = Database(settings.database_url)
    hub = ConnectionHub()
    keys = settings.token_encryption_keys.get_secret_value()
    cipher = TokenCipher(keys) if keys else None
    yandex: YandexProviderBuilder | None = None
    if cipher is not None:
        from app.providers.yandex import YandexProviderPool  # noqa: PLC0415 — тяжёлый импорт по требованию

        yandex = YandexProviderPool(settings, cipher)
    return AppContext(
        settings=settings,
        db=db,
        clock=clock,
        hub=hub,
        rooms=RoomManager(db, clock, AsyncioTimers(), hub),
        providers=ProviderFactory(settings.music_provider, yandex),
        cipher=cipher,
        search_limiter=RateLimiter(rate=3, burst=10, monotonic=clock.monotonic),
        stream_limiter=RateLimiter(rate=2, burst=10, monotonic=clock.monotonic),
    )


def create_app(settings: Settings | None = None, ctx: AppContext | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level, json=settings.log_json)
        context = ctx or build_context(settings)
        app.state.ctx = context
        if settings.db_auto_create:
            await context.db.create_all()
        janitor = asyncio.create_task(context.rooms.run_janitor())
        log.info(
            "startup",
            env=settings.env,
            provider=settings.music_provider,
            audio_mode=settings.audio_mode,
        )
        try:
            yield
        finally:
            janitor.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await janitor
            await context.rooms.shutdown()
            await asyncio.sleep(0.05)  # дать писателям WS отправить close-фреймы
            await context.db.dispose()
            log.info("shutdown")

    app = FastAPI(
        title="Слушаем вместе",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.is_prod else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.is_prod else "/api/openapi.json",
    )

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse({"code": exc.code, "message": exc.message}, status_code=exc.status_code)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or secrets.token_hex(8)
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            # CSRF: изменяющие запросы принимаем только со своего Origin (SPEC §7.6).
            if request.method in UNSAFE_METHODS and request.url.path.startswith("/api/"):
                origin = request.headers.get("origin")
                if origin not in settings.allowed_origins:
                    return JSONResponse(
                        {"code": "bad_origin", "message": "Запрос с чужого сайта отклонён."},
                        status_code=403,
                    )
            response = await call_next(request)
            if request.url.path.startswith(("/api/stream", "/api/auth")):
                response.headers["Cache-Control"] = "no-store"
            response.headers["X-Request-Id"] = request_id
            return response
        finally:
            structlog.contextvars.unbind_contextvars("request_id")

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(rooms_router)
    app.include_router(music_router)
    app.include_router(ws_router)
    if settings.allow_dev_login:
        app.mount(
            FAKE_MEDIA_URL,
            StaticFiles(directory=FAKE_MEDIA_DIR, check_dir=False),
            name="fake-media",
        )
    return app


app = create_app()
