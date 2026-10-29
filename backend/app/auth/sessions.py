"""Сессии на cookie (SPEC §4.1): непредсказуемый идентификатор, 30 дней со скользящим продлением.

В cookie — случайный токен; в БД — только HMAC от него, так что утечка БД не даёт войти.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Session, User, utcnow

COOKIE_NAME = "mt_session"
SESSION_TTL = timedelta(days=30)
SLIDING_REFRESH_AFTER = timedelta(hours=12)


def _session_id(raw_token: str, secret: str) -> str:
    return hmac.new(secret.encode(), raw_token.encode(), hashlib.sha256).hexdigest()


async def create_session(db: AsyncSession, user: User, secret: str) -> tuple[str, datetime]:
    raw = secrets.token_urlsafe(32)
    expires = utcnow() + SESSION_TTL
    db.add(Session(id=_session_id(raw, secret), user_id=user.id, expires_at=expires))
    await db.commit()
    return raw, expires


async def resolve_session(
    db: AsyncSession, raw_token: str, secret: str
) -> tuple[User, datetime | None] | None:
    """Пользователь по cookie и новый срок, если сессию продлили (тогда переписать cookie)."""
    if not raw_token or len(raw_token) > 128:
        return None
    session = await db.get(Session, _session_id(raw_token, secret))
    if session is None:
        return None
    now = utcnow()
    if session.expires_at <= now:
        await db.delete(session)
        await db.commit()
        return None
    renewed: datetime | None = None
    if now - session.last_seen_at >= SLIDING_REFRESH_AFTER:
        session.last_seen_at = now
        session.expires_at = now + SESSION_TTL
        renewed = session.expires_at
        await db.commit()
    return session.user, renewed


async def delete_session(db: AsyncSession, raw_token: str, secret: str) -> None:
    await db.execute(delete(Session).where(Session.id == _session_id(raw_token, secret)))
    await db.commit()


async def delete_expired_sessions(db: AsyncSession) -> int:
    result = await db.execute(select(Session.id).where(Session.expires_at <= utcnow()))
    ids = list(result.scalars())
    if ids:
        await db.execute(delete(Session).where(Session.id.in_(ids)))
        await db.commit()
    return len(ids)
