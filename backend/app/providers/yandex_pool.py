"""Пул YandexProvider: экземпляр на пользователя, общий кеш публичных метаданных,
общий лимитер запросов, обновление токена через refresh_token с записью в БД."""

from __future__ import annotations

import time

from app.auth.crypto import TokenCipher, TokenCipherError
from app.auth.yandex_login import apply_token, forget_tokens
from app.auth.yandex_oauth import YandexAuth
from app.core.config import Settings
from app.core.logging import get_logger
from app.core.ratelimit import RateLimiter
from app.db.models import User
from app.db.session import Database
from app.providers.base import MusicProvider, ProviderAuthError, ProviderError
from app.providers.yandex import TTLCache, YandexProvider, token_fingerprint

log = get_logger(__name__)

PROVIDER_TTL_S = 30 * 60
# Ориентир — живой клиент: десятки запросов при открытии плейлиста, не сотни.
REQUESTS_PER_SECOND = 8
REQUESTS_BURST = 25


class YandexProviderPool:
    def __init__(
        self, settings: Settings, cipher: TokenCipher, db: Database, auth: YandexAuth
    ) -> None:
        self._settings = settings
        self._cipher = cipher
        self._db = db
        self._auth = auth
        self._public = TTLCache()
        self._limiter = RateLimiter(REQUESTS_PER_SECOND, REQUESTS_BURST, time.monotonic)
        self._providers: dict[str, tuple[str, float, YandexProvider]] = {}

    def __call__(self, user: User) -> MusicProvider:
        if not user.token_enc:
            raise ProviderAuthError
        try:
            token = self._cipher.decrypt(user.token_enc)
        except TokenCipherError as e:
            raise ProviderAuthError from e
        fingerprint = token_fingerprint(token)
        now = time.monotonic()
        cached = self._providers.get(user.id)
        if cached and cached[0] == fingerprint and now - cached[1] < PROVIDER_TTL_S:
            return cached[2]
        user_id = user.id

        async def refresher() -> str | None:
            return await self.refresh(user_id)

        provider = YandexProvider(
            user_key=user.id,
            uid=user.external_id,
            token=token,
            proxy_url=self._settings.ym_proxy_url,
            public_cache=self._public,
            limiter=self._limiter,
            refresher=refresher,
        )
        self._providers[user.id] = (fingerprint, now, provider)
        if len(self._providers) > 500:
            stale = [k for k, v in self._providers.items() if now - v[1] > PROVIDER_TTL_S]
            for key in stale:
                del self._providers[key]
        return provider

    async def refresh(self, user_id: str) -> str | None:
        """Обновить токен по refresh_token. Неудача → токены стираются, нужен повторный вход."""
        async with self._db.sessionmaker() as db:
            user = await db.get(User, user_id)
            if user is None or not user.refresh_token_enc:
                return None
            try:
                refresh_token = self._cipher.decrypt(user.refresh_token_enc)
                token = await self._auth.refresh(refresh_token)
            except (TokenCipherError, ProviderError):
                log.info("yandex_token_refresh_failed", user_id=user_id)
                forget_tokens(user)
                await db.commit()
                self._providers.pop(user_id, None)
                return None
            apply_token(user, self._cipher, token)
            await db.commit()
            log.info("yandex_token_refreshed", user_id=user_id)
            return token.access_token
