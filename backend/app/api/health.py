"""Проверки живости и готовности."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Процесс жив."""
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict[str, str]:
    """Готов принимать трафик. Проверка БД появится вместе с БД в фазе 1."""
    return {"status": "ok"}
