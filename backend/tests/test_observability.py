from pydantic import SecretStr

from app.core.config import Environment, MusicProviderKind, Settings
from app.core.logging import mask_secrets
from app.core.observability import _scrub, validate_settings


def prod(**kw: object) -> Settings:
    base: dict[str, object] = {
        "env": Environment.PROD,
        "public_origin": "https://music.example.com",
        "session_secret": SecretStr("x" * 48),
        "music_provider": MusicProviderKind.FAKE,
    }
    return Settings.model_validate(base | kw)


def test_dev_settings_are_not_validated() -> None:
    assert validate_settings(Settings(env=Environment.DEV)) == []


def test_prod_requires_secret_https_and_keys() -> None:
    assert validate_settings(prod()) == []
    problems = validate_settings(
        prod(
            session_secret=SecretStr("short"),
            public_origin="http://music.example.com",
            music_provider=MusicProviderKind.YANDEX,
        )
    )
    assert len(problems) == 3


def test_log_processor_masks_tokens_and_secret_keys() -> None:
    event = {
        "event": "login",
        "token": "y0_AgAAAAB-secret-value-1234567890",
        "detail": "Authorization: Bearer abc.def and y0_AgAAAAB-secret-value-1234567890",
        "user_id": "u1",
    }
    masked = mask_secrets(None, "info", dict(event))
    assert masked["token"] == "***"
    assert "y0_" not in masked["detail"]
    assert "abc.def" not in masked["detail"]
    assert masked["user_id"] == "u1"


def test_sentry_scrubber_removes_cookies_and_tokens() -> None:
    event = {
        "message": "failed for y0_AgAAAAB-secret-value-1234567890",
        "request": {"cookies": {"mt_session": "x"}, "headers": {"Cookie": "mt_session=x"}},
    }
    out = _scrub(event, None)
    assert "cookies" not in out["request"]
    assert out["request"]["headers"]["Cookie"] == "***"
    assert "y0_" not in out["message"]
