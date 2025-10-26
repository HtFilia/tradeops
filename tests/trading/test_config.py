import os
from contextlib import nullcontext

import pytest

from trading.config import TradingSettings

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("env", "expectation"),
    [
        ({"TRADING_REDIS_URL": "redis://localhost:6379/1"}, nullcontext()),
        (
            {"TRADING_REDIS_URL": "redis://localhost:6379/1", "TRADING_POSTGRES_DSN": ""},
            pytest.raises(ValueError),
        ),
    ],
)
def test_settings_validation(monkeypatch: pytest.MonkeyPatch, env: dict[str, str], expectation) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with expectation:
        settings = TradingSettings.from_env()
        assert settings.redis_url == env.get("TRADING_REDIS_URL", settings.redis_url)


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("TRADING_"):
            monkeypatch.delenv(key, raising=False)
    settings = TradingSettings.from_env()
    assert settings.order_stream == "order_commands"
    assert settings.marketdata_stream == "marketdata_stream"
    assert settings.cors_origins == ["http://localhost:5173"]
    assert settings.session_cookie_name == "session_id"
    assert settings.session_ttl_minutes == 60


def test_settings_parses_cors_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_CORS_ORIGINS", "http://localhost:3000, https://app.example.com")
    settings = TradingSettings.from_env()
    assert settings.cors_origins == ["http://localhost:3000", "https://app.example.com"]
