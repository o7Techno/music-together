"""YandexProvider — реализуется в фазе 2. Пока фабрика отказывает с понятной ошибкой."""

from __future__ import annotations

from app.auth.crypto import TokenCipher
from app.core.config import Settings
from app.db.models import User
from app.providers.base import MusicProvider, ProviderAuthError


class YandexProviderPool:
    def __init__(self, settings: Settings, cipher: TokenCipher) -> None:
        self._settings = settings
        self._cipher = cipher

    def __call__(self, user: User) -> MusicProvider:
        raise ProviderAuthError
