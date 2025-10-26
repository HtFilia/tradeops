from __future__ import annotations

import os
from typing import Any

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
