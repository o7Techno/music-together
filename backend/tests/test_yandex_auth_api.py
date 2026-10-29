"""REST входа через Яндекс с подменённым OAuth (без сети)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.auth.crypto import TokenCipher
from app.auth.yandex_oauth import DeviceCodeData, DeviceFlowError, TokenData
from app.core.config import MusicProviderKind, Settings
from app.db.models import User
from app.db.session import Database
from app.main import build_context
from app.providers.base import ProviderAuthError, UserProfile
from tests.live import ORIGIN, create_schema, live_server, make_settings

TOKEN = "y0_AgAAAAB_fake_access_token_1234567890"


class FakeAuth:
    def __init__(self) -> None:
        self.pending_polls = 1
        self.deny = False
        self.has_plus = True

    async def request_device_code(self) -> DeviceCodeData:
        return DeviceCodeData("dev-code-secret", "abcd1234", "https://ya.ru/device", 300, 0)

    async def poll_device_token(self, device_code: str) -> TokenData | None:
        assert device_code == "dev-code-secret"
        if self.deny:
            raise DeviceFlowError
        if self.pending_polls > 0:
            self.pending_polls -= 1
            return None
        return TokenData(TOKEN, "refresh-secret", 31_536_000)

    async def refresh(self, refresh_token: str) -> TokenData:
        raise ProviderAuthError

    async def profile(self, access_token: str) -> UserProfile:
        if access_token != TOKEN:
            raise ProviderAuthError("Токен не подходит — проверьте, что скопировали его целиком.")
        return UserProfile(
            external_id="555",
            login="anna",
            display_name="Аня",
            avatar_url="https://avatars.yandex.net/get-yapic/1/islands-200",
            has_plus=self.has_plus,
        )


@pytest.fixture
def yandex_settings(tmp_path: Path) -> Settings:
    db_path = tmp_path / "ya.db"
    asyncio.run(create_schema(db_path))
    return make_settings(db_path).model_copy(
        update={
            "music_provider": MusicProviderKind.YANDEX,
            "token_encryption_keys": SecretStr(TokenCipher.generate_key()),
        }
    )


@pytest.fixture
def fake_auth() -> FakeAuth:
    return FakeAuth()


@pytest.fixture
def ya_server(yandex_settings: Settings, fake_auth: FakeAuth) -> Iterator[str]:
    ctx = build_context(yandex_settings)
    ctx.yandex_auth = fake_auth
    with live_server(yandex_settings, ctx) as base:
        yield base


def client(base: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base, headers={"Origin": ORIGIN})


async def test_auth_config_offers_yandex_and_hides_dev_login(ya_server: str) -> None:
    async with client(ya_server) as http:
        cfg = (await http.get("/api/auth/config")).json()
    assert cfg == {"devLogin": True, "yandexLogin": True}  # ENV=test — dev-логин разрешён


async def test_device_flow_logs_in_and_stores_encrypted_token(
    ya_server: str, yandex_settings: Settings
) -> None:
    async with client(ya_server) as http:
        start = (await http.post("/api/auth/device/start")).json()
        assert start["userCode"] == "abcd1234"
        assert start["verificationUrl"] == "https://ya.ru/device"
        assert "dev-code-secret" not in str(start)  # device_code не уходит на фронт

        first = (await http.post("/api/auth/device/poll", json={"flowId": start["flowId"]})).json()
        assert first["status"] == "pending"
        await asyncio.sleep(0.25)
        done = (await http.post("/api/auth/device/poll", json={"flowId": start["flowId"]})).json()
        assert done["status"] == "ok"
        assert done["me"]["displayName"] == "Аня"
        assert done["me"]["providerConnected"] is True
        assert "mt_session" in http.cookies
        me = (await http.get("/api/auth/me")).json()
        assert me["hasPlus"] is True
        assert TOKEN not in str(me)

        again = (await http.post("/api/auth/device/poll", json={"flowId": start["flowId"]})).json()
        assert again["status"] == "expired"  # одноразовый flow

    db = Database(yandex_settings.database_url)
    async with db.sessionmaker() as s:
        user = (await s.execute(select(User).where(User.external_id == "555"))).scalar_one()
    await db.dispose()
    assert user.token_enc is not None
    assert TOKEN not in user.token_enc
    cipher = TokenCipher(yandex_settings.token_encryption_keys.get_secret_value())
    assert cipher.decrypt(user.token_enc) == TOKEN
    assert user.refresh_token_enc is not None


async def test_denied_device_flow_reports_expired(ya_server: str, fake_auth: FakeAuth) -> None:
    fake_auth.deny = True
    async with client(ya_server) as http:
        start = (await http.post("/api/auth/device/start")).json()
        res = (await http.post("/api/auth/device/poll", json={"flowId": start["flowId"]})).json()
    assert res["status"] == "expired"


async def test_unknown_flow_is_expired(ya_server: str) -> None:
    async with client(ya_server) as http:
        res = await http.post("/api/auth/device/poll", json={"flowId": "x" * 20})
    assert res.json()["status"] == "expired"


async def test_token_login_and_bad_token(ya_server: str, fake_auth: FakeAuth) -> None:
    fake_auth.has_plus = False
    async with client(ya_server) as http:
        bad = await http.post(
            "/api/auth/token-login", json={"token": "y0_wrong_token_value_123456"}
        )
        assert bad.status_code == 401
        assert "Токен не подходит" in bad.json()["message"]
        ok = await http.post("/api/auth/token-login", json={"token": TOKEN})
        assert ok.status_code == 200
        assert ok.json()["hasPlus"] is False


async def test_csrf_rejects_foreign_origin(ya_server: str) -> None:
    async with httpx.AsyncClient(
        base_url=ya_server, headers={"Origin": "https://evil.example"}
    ) as http:
        res = await http.post("/api/auth/token-login", json={"token": TOKEN})
    assert res.status_code == 403
    assert res.json()["code"] == "bad_origin"
