"""Конфигурация приложения. Всё — только из переменных окружения (см. `.env.example`)."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class MusicProviderKind(StrEnum):
    YANDEX = "yandex"
    FAKE = "fake"


class AudioMode(StrEnum):
    DIRECT = "direct"
    PROXY = "proxy"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Environment = Environment.DEV
    log_level: str = "INFO"
    log_json: bool = False

    database_url: str = "postgresql+asyncpg://music:music@localhost:5432/music"
    # Создать таблицы при старте (только для e2e/локальных SQLite-запусков; в проде — Alembic).
    db_auto_create: bool = False

    # Публичный origin фронтенда: используется для проверки Origin у WS и изменяющих REST-запросов.
    public_origin: str = "http://localhost:5173"
    extra_allowed_origins: list[str] = Field(default_factory=list)

    session_secret: SecretStr = SecretStr("dev-insecure-session-secret-change-me")
    # Один или несколько Fernet-ключей через запятую; первый используется для шифрования.
    token_encryption_keys: SecretStr = SecretStr("")

    music_provider: MusicProviderKind = MusicProviderKind.FAKE
    audio_mode: AudioMode = AudioMode.DIRECT
    ym_proxy_url: str | None = None

    sentry_dsn: str | None = None

    @property
    def is_prod(self) -> bool:
        return self.env is Environment.PROD

    @property
    def allowed_origins(self) -> set[str]:
        return {self.public_origin, *self.extra_allowed_origins}

    @property
    def cookie_secure(self) -> bool:
        return self.is_prod or self.public_origin.startswith("https://")

    @property
    def allow_dev_login(self) -> bool:
        """Вход без Яндекса: в разработке и на FakeProvider (демо/e2e), но не в проде с Яндексом."""
        return self.music_provider is MusicProviderKind.FAKE or not self.is_prod


@lru_cache
def get_settings() -> Settings:
    return Settings()
