"""Вход через Яндекс: хранение незавершённых Device Flow, сохранение пользователя и токенов."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.crypto import TokenCipher
from app.auth.yandex_oauth import DeviceCodeData, TokenData
from app.db.models import User, utcnow
from app.providers.base import UserProfile

MAX_PENDING_FLOWS = 1000


@dataclass
class PendingFlow:
    device_code: str
    expires_at: float
    interval: float
    last_poll: float = field(default=0.0)


class DeviceFlowStore:
    """Незавершённые входы: в памяти процесса (один инстанс бэкенда, SPEC §2).

    Клиенту отдаётся только случайный `flow_id`; `device_code` остаётся на сервере.
    """

    def __init__(self) -> None:
        self._flows: dict[str, PendingFlow] = {}

    def add(self, code: DeviceCodeData) -> str:
        self.prune()
        if len(self._flows) >= MAX_PENDING_FLOWS:
            oldest = min(self._flows, key=lambda k: self._flows[k].expires_at)
            del self._flows[oldest]
        flow_id = secrets.token_urlsafe(24)
        self._flows[flow_id] = PendingFlow(
            device_code=code.device_code,
            expires_at=time.monotonic() + code.expires_in,
            interval=max(0.2, float(code.interval)),
        )
        return flow_id

    def get(self, flow_id: str) -> PendingFlow | None:
        flow = self._flows.get(flow_id)
        if flow is None or flow.expires_at < time.monotonic():
            self._flows.pop(flow_id, None)
            return None
        return flow

    def too_early(self, flow: PendingFlow) -> bool:
        """Не опрашивать Яндекс чаще рекомендованного интервала, сколько бы ни поллил фронт."""
        now = time.monotonic()
        if now - flow.last_poll < flow.interval * 0.8:
            return True
        flow.last_poll = now
        return False

    def remove(self, flow_id: str) -> None:
        self._flows.pop(flow_id, None)

    def prune(self) -> None:
        now = time.monotonic()
        for key in [k for k, f in self._flows.items() if f.expires_at < now]:
            del self._flows[key]


async def upsert_yandex_user(
    db: AsyncSession, cipher: TokenCipher, profile: UserProfile, token: TokenData
) -> User:
    """Создать или обновить пользователя по uid Яндекса; токены — только в зашифрованном виде."""
    user = (
        await db.execute(
            select(User).where(User.provider == "yandex", User.external_id == profile.external_id)
        )
    ).scalar_one_or_none()
    if user is None:
        user = User(provider="yandex", external_id=profile.external_id)
        db.add(user)
    user.login = profile.login
    user.display_name = profile.display_name
    user.avatar_url = profile.avatar_url
    user.has_plus = profile.has_plus
    apply_token(user, cipher, token)
    await db.commit()
    return user


def apply_token(user: User, cipher: TokenCipher, token: TokenData) -> None:
    user.token_enc = cipher.encrypt(token.access_token)
    if token.refresh_token:
        user.refresh_token_enc = cipher.encrypt(token.refresh_token)
    user.token_expires_at = (
        utcnow() + timedelta(seconds=token.expires_in) if token.expires_in else None
    )


def forget_tokens(user: User) -> None:
    user.token_enc = None
    user.refresh_token_enc = None
    user.token_expires_at = None
