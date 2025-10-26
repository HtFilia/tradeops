from __future__ import annotations

import os
from typing import Any

from datetime import timedelta

from auth.constants import SESSION_COOKIE_NAME
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class TradingSettings(BaseModel):
    redis_url: str = Field(default="redis://localhost:6379/0", alias="TRADING_REDIS_URL")
    postgres_dsn: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/trading",
        alias="TRADING_POSTGRES_DSN",
    )
    marketdata_stream: str = Field(default="marketdata_stream", alias="TRADING_MARKETDATA_STREAM")
    execution_stream: str = Field(default="execution_stream", alias="TRADING_EXECUTION_STREAM")
    order_stream: str = Field(default="order_commands", alias="TRADING_ORDER_STREAM")
    health_port: int = Field(default=8081, alias="TRADING_HEALTH_PORT")
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173"],
        alias="TRADING_CORS_ORIGINS",
    )
    session_cookie_name: str = Field(
        default=SESSION_COOKIE_NAME,
        alias="TRADING_SESSION_COOKIE_NAME",
    )
    session_ttl_minutes: int = Field(default=60, alias="TRADING_SESSION_TTL_MINUTES")

    model_config = ConfigDict(
        frozen=True,
        populate_by_name=True,
        extra="ignore",
    )

    @field_validator("redis_url", "postgres_dsn")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("connection strings must not be empty")
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: Any) -> list[str]:
        if value is None:
            return ["http://localhost:5173"]
        if isinstance(value, str):
            parts = [origin.strip() for origin in value.split(",") if origin.strip()]
            return parts or ["http://localhost:5173"]
        if isinstance(value, (list, tuple, set)):
            return [str(origin) for origin in value if str(origin).strip()]
        raise ValueError("cors_origins must be a comma separated string or list of strings")

    @field_validator("session_ttl_minutes")
    @classmethod
    def _validate_ttl(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("session_ttl_minutes must be positive")
        return value

    @property
    def session_ttl(self) -> timedelta:
        return timedelta(minutes=self.session_ttl_minutes)


    @classmethod
    def from_env(cls) -> "TradingSettings":
        kwargs: dict[str, Any] = {}
        for field_name, field in cls.model_fields.items():
            alias = field.alias or field_name
            raw_value = os.getenv(alias)
            if raw_value is not None:
                kwargs[field_name] = raw_value
        return cls(**kwargs)


def load_settings() -> TradingSettings:
    try:
        return TradingSettings.from_env()
    except ValidationError as exc:  # pragma: no cover - re-raise with context
        raise ValueError(f"Invalid trading settings: {exc}") from exc
