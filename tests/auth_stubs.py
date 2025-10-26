from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from auth.models import AuthenticatedSession, User
from auth.session import SessionStore, SessionToken
from auth.storage import AccountRepository, UserRepository


@dataclass(slots=True)
class StubUser(UserRepository):
    created: list[User]
    existing: dict[str, User]

    def __init__(self) -> None:
        self.created = []
        self.existing = {}

    async def get_by_email(self, email: str) -> User | None:
        return self.existing.get(email)

    async def create(self, email: str, password_hash: str) -> User:
        user = User(
            id=f"user-{len(self.created) + 1}",
            email=email,
            password_hash=password_hash,
            created_at=datetime.now(timezone.utc),
        )
        self.created.append(user)
        self.existing[email] = user
        return user


@dataclass(slots=True)
class StubAccount(AccountRepository):
    created_accounts: list[tuple[str, Decimal, str]]

    def __init__(self) -> None:
        self.created_accounts = []

    async def create_account(self, user_id: str, starting_balance: Decimal, currency: str) -> None:
        self.created_accounts.append((user_id, starting_balance, currency))


@dataclass(slots=True)
class StubSession(SessionStore):
    issued: list[AuthenticatedSession]
    revoked_tokens: list[SessionToken]
    ttl: timedelta

    def __init__(self, ttl: timedelta) -> None:
        self.issued = []
        self.revoked_tokens = []
        self.ttl = ttl

    async def issue(self, user_id: str) -> AuthenticatedSession:
        token = SessionToken(value=f"session-{len(self.issued) + 1}")
        expires_at = datetime.now(timezone.utc) + self.ttl
        session = AuthenticatedSession(token=token, user_id=user_id, expires_at=expires_at)
        self.issued.append(session)
        return session

    async def revoke(self, token: SessionToken) -> None:
        self.revoked_tokens.append(token)

    async def get(self, token: SessionToken) -> AuthenticatedSession | None:
        for session in self.issued:
            if session.token == token:
                return session
        return None


__all__ = ["StubAccount", "StubSession", "StubUser"]
