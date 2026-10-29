"""Точка входа FastAPI-приложения."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.log_json)
    get_logger(__name__).info(
        "startup",
        env=settings.env,
        provider=settings.music_provider,
        audio_mode=settings.audio_mode,
    )
    yield
    get_logger(__name__).info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(title="Слушаем вместе", version="0.1.0", lifespan=lifespan)
    app.include_router(health_router)
    return app


app = create_app()
