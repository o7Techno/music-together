"""OAuth Яндекса для входа (SPEC §4.1): Device Flow, обновление токена, профиль.

Device Flow — средствами `yandex-music` (request_device_code / poll_device_token, DECISIONS D-005).
Всё спрятано за протоколом `YandexAuth`, чтобы REST-слой тестировался без сети.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx
from yandex_music.exceptions import DeviceAuthError, UnauthorizedError, YandexMusicError

from app.core.logging import get_logger
from app.providers.base import ProviderAuthError, ProviderError, UserProfile
from app.providers.yandex import make_client

log = get_logger(__name__)

OAUTH_TOKEN_URL = "https://oauth.yandex.ru/token"  # noqa: S105 — URL, не секрет
LOGIN_INFO_URL = "https://login.yandex.ru/info?format=json"
# Публичные OAuth-креды официального Android-приложения Яндекс Музыки — те же, что использует
# библиотека для Device Flow; нужны для обмена refresh_token.
ANDROID_CLIENT_ID = "23cabbbdc6cd418abb4b39c32c41195d"
ANDROID_CLIENT_SECRET = "53bc75238f0c4d08a118e51fe9203300"  # noqa: S105 — публичный секрет клиента
DEVICE_NAME = "Слушаем вместе"


@dataclass(frozen=True)
class DeviceCodeData:
    device_code: str
    user_code: str
    verification_url: str
    expires_in: int
    interval: int


@dataclass(frozen=True)
class TokenData:
    access_token: str
    refresh_token: str | None
    expires_in: int | None


class DeviceFlowError(ProviderError):
    code = "device_flow"
    status_code = 400
    default_message = "Код входа устарел или вход отклонён — начните заново."


class YandexAuth(Protocol):
    async def request_device_code(self) -> DeviceCodeData: ...

    async def poll_device_token(self, device_code: str) -> TokenData | None: ...

    async def refresh(self, refresh_token: str) -> TokenData: ...

    async def profile(self, access_token: str) -> UserProfile: ...


class YandexAuthClient:
    def __init__(self, proxy_url: str | None) -> None:
        self._proxy = proxy_url or None

    async def request_device_code(self) -> DeviceCodeData:
        client = make_client(None, self._proxy)
        try:
            code = await client.request_device_code(device_name=DEVICE_NAME)
        except YandexMusicError as e:
            raise ProviderError from e
        return DeviceCodeData(
            device_code=code.device_code,
            user_code=code.user_code,
            verification_url=code.verification_url,
            expires_in=int(code.expires_in),
            interval=int(code.interval),
        )

    async def poll_device_token(self, device_code: str) -> TokenData | None:
        client = make_client(None, self._proxy)
        try:
            token = await client.poll_device_token(device_code)
        except DeviceAuthError as e:
            raise DeviceFlowError from e
        except YandexMusicError as e:
            raise ProviderError from e
        if token is None:
            return None
        return TokenData(token.access_token, token.refresh_token, token.expires_in)

    async def refresh(self, refresh_token: str) -> TokenData:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": ANDROID_CLIENT_ID,
            "client_secret": ANDROID_CLIENT_SECRET,
        }
        async with httpx.AsyncClient(timeout=10, proxy=self._proxy) as http:
            r = await http.post(OAUTH_TOKEN_URL, data=data)
        if r.status_code != 200:
            raise ProviderAuthError
        body = r.json()
        return TokenData(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token") or refresh_token,
            expires_in=body.get("expires_in"),
        )

    async def profile(self, access_token: str) -> UserProfile:
        try:
            client = await make_client(access_token, self._proxy).init()
        except UnauthorizedError as e:
            raise ProviderAuthError(
                "Токен не подходит — проверьте, что скопировали его целиком."
            ) from e
        except YandexMusicError as e:
            raise ProviderError from e
        status = client.me
        account = status.account if status else None
        if account is None or account.uid is None:
            raise ProviderAuthError
        avatar_url = await self._avatar(access_token)
        return UserProfile(
            external_id=str(account.uid),
            login=account.login or str(account.uid),
            display_name=account.display_name or account.full_name or account.login or "Слушатель",
            avatar_url=avatar_url,
            has_plus=bool(status.plus and status.plus.has_plus) if status else False,
        )

    async def _avatar(self, access_token: str) -> str | None:
        """Аватар из Яндекс ID. Из ответа берём только id аватара — остальные данные не храним."""
        try:
            async with httpx.AsyncClient(timeout=5, proxy=self._proxy) as http:
                r = await http.get(
                    LOGIN_INFO_URL, headers={"Authorization": f"OAuth {access_token}"}
                )
            if r.status_code != 200:
                return None
            body = r.json()
        except (httpx.HTTPError, ValueError):
            return None
        avatar_id = body.get("default_avatar_id")
        if not avatar_id or body.get("is_avatar_empty"):
            return None
        return f"https://avatars.yandex.net/get-yapic/{avatar_id}/islands-200"
