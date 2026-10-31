"""Выбор провайдера по конфигу. Провайдер создаётся на пользователя — запросы идут его токеном."""

from __future__ import annotations

from typing import Protocol

from app.core.config import MusicProviderKind
from app.db.models import User
from app.providers.base import MusicProvider, ProviderAuthError
from app.providers.fake import FakeProvider, FakeWorld


class YandexProviderBuilder(Protocol):
    def __call__(self, user: User) -> MusicProvider: ...


class ProviderFactory:
    def __init__(
        self, kind: MusicProviderKind, yandex: YandexProviderBuilder | None = None
    ) -> None:
        self.kind = kind
        self._yandex = yandex
        self.fake_world = FakeWorld()

    def for_user(self, user: User) -> MusicProvider:
        if self.kind is MusicProviderKind.FAKE or user.provider == "dev":
            return FakeProvider(user.id, self.fake_world)
        if self._yandex is None:
            raise ProviderAuthError
        return self._yandex(user)
