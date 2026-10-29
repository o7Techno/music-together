"""Проверки живости и готовности."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.deps import Ctx

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Процесс жив."""
    return {"status": "ok"}


@router.get("/ready", response_model=None)
async def ready(ctx: Ctx) -> dict[str, str] | JSONResponse:
    """Готов принимать трафик: БД доступна."""
    if not await ctx.db.ping():
        return JSONResponse({"status": "db_unavailable"}, status_code=503)
    return {"status": "ok"}
