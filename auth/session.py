from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Final
from uuid import uuid4

try:  # pragma: no cover - import guard, redis is required in production environment
    from redis.asyncio import Redis  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback for tests without redis
    Redis = None  # type: ignore[assignment]

from .models import AuthenticatedSession


@dataclass(slots=True, frozen=True)
class SessionToken:
    value: str

    def __str__(self) -> str:
        return self.value


class SessionStore(ABC):
    """Abstract base class for issuing and managing authenticated sessions."""

    @abstractmethod
    async def issue(self, user_id: str) -> AuthenticatedSession:
        ...

    @abstractmethod
    async def get(self, token: SessionToken) -> AuthenticatedSession | None:
        ...

    @abstractmethod
    async def revoke(self, token: SessionToken) -> None:
        ...


class RedisSessionStore(SessionStore):
    """Redis-backed session store for HTTP-only cookie sessions."""

    _SESSION_PREFIX: Final[str] = "auth_session:"

    def __init__(self, redis: Redis, ttl: timedelta) -> None:
        if Redis is None:  # pragma: no cover - guard
            raise RuntimeError("redis library is required but not installed")
        self._redis = redis
        self._ttl = ttl

    async def issue(self, user_id: str) -> AuthenticatedSession:
        token = SessionToken(value=uuid4().hex)
        expires_at = datetime.now(timezone.utc) + self._ttl
        payload = json.dumps({"user_id": user_id, "expires_at": expires_at.isoformat()})
        await self._redis.setex(self._key(token), int(self._ttl.total_seconds()), payload)
        return AuthenticatedSession(token=token, user_id=user_id, expires_at=expires_at)

    async def get(self, token: SessionToken) -> AuthenticatedSession | None:
        raw = await self._redis.get(self._key(token))
        if raw is None:
            return None
        document = json.loads(raw)
        expires_at = datetime.fromisoformat(document["expires_at"])
        return AuthenticatedSession(
            token=token,
            user_id=document["user_id"],
            expires_at=expires_at,
        )

    async def revoke(self, token: SessionToken) -> None:
        await self._redis.delete(self._key(token))

    def _key(self, token: SessionToken) -> str:
        return f"{self._SESSION_PREFIX}{token.value}"


__all__ = ["SessionStore", "SessionToken", "RedisSessionStore"]
