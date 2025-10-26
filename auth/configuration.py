from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping

from .constants import SESSION_COOKIE_NAME


@dataclass(slots=True)
class AuthConfig:
    """Configuration options for the Auth & User Management agent."""

    starting_balance: Decimal
    base_currency: str
    session_ttl_minutes: int
    secure_cookies: bool = True
    session_cookie_name: str = SESSION_COOKIE_NAME
    session_cookie_domain: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "AuthConfig":
        """Construct configuration from environment variables."""
        balance_raw = env.get("AUTH_STARTING_BALANCE", "1000000")
        try:
            starting_balance = Decimal(balance_raw)
        except (InvalidOperation, ValueError) as exc:  # pragma: no cover - defensive
            raise ValueError(f"Invalid AUTH_STARTING_BALANCE: {balance_raw}") from exc

        base_currency = env.get("AUTH_BASE_CURRENCY", "USD")
        ttl_raw = env.get("AUTH_SESSION_TTL_MINUTES", "30")
        try:
            ttl_minutes = int(ttl_raw)
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(f"Invalid AUTH_SESSION_TTL_MINUTES: {ttl_raw}") from exc

        secure_cookies = env.get("AUTH_SECURE_COOKIES", "true").lower() in {"1", "true", "yes"}
        cookie_name = env.get("AUTH_SESSION_COOKIE_NAME", SESSION_COOKIE_NAME)
        cookie_domain = env.get("AUTH_SESSION_COOKIE_DOMAIN")

        return cls(
            starting_balance=starting_balance,
            base_currency=base_currency,
            session_ttl_minutes=ttl_minutes,
            secure_cookies=secure_cookies,
            session_cookie_name=cookie_name,
            session_cookie_domain=cookie_domain,
        )


__all__ = ["AuthConfig"]
