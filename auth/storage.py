from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol, TYPE_CHECKING

from auth.models import User

if TYPE_CHECKING:
    import asyncpg


class SupportsAcquire(Protocol):
    def acquire(self) -> Any:
        ...


class UserRepository(ABC):
    """Abstract repository interface for user records."""

    @abstractmethod
    async def get_by_email(self, email: str) -> User | None:
        ...

    @abstractmethod
    async def create(self, email: str, password_hash: str) -> User:
        ...


class AccountRepository(ABC):
    """Abstract repository interface for account rows."""

    @abstractmethod
    async def create_account(self, user_id: str, starting_balance: Decimal, currency: str) -> None:
        ...


@dataclass(slots=True)
class PostgresUserRepository(UserRepository):
    pool: SupportsAcquire
    schema: str = "public"

    async def get_by_email(self, email: str) -> User | None:
        query = f"""
        SELECT id, email, password_hash, created_at
        FROM {self.schema}.users
        WHERE email = $1
        """
        async with self.pool.acquire() as conn:  # type: ignore[attr-defined]
            row = await conn.fetchrow(query, email)
        if row is None:
            return None
        created_at = row["created_at"]
        if isinstance(created_at, datetime):
            created_at_dt = created_at
        else:  # pragma: no cover - asyncpg returns datetime
            created_at_dt = datetime.fromisoformat(created_at)
        if created_at_dt.tzinfo is None:
            created_at_dt = created_at_dt.replace(tzinfo=timezone.utc)
        return User(
            id=str(row["id"]),
            email=row["email"],
            password_hash=row["password_hash"],
            created_at=created_at_dt,
        )

    async def create(self, email: str, password_hash: str) -> User:
        query = f"""
        INSERT INTO {self.schema}.users (email, password_hash)
        VALUES ($1, $2)
        RETURNING id, email, password_hash, created_at
        """
        async with self.pool.acquire() as conn:  # type: ignore[attr-defined]
            row = await conn.fetchrow(query, email, password_hash)
        created_at: datetime = row["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return User(
            id=str(row["id"]),
            email=row["email"],
            password_hash=row["password_hash"],
            created_at=created_at,
        )


@dataclass(slots=True)
class PostgresAccountRepository(AccountRepository):
    pool: SupportsAcquire
    schema: str = "public"

    async def create_account(
        self,
        user_id: str,
        starting_balance: Decimal,
        currency: str,
        margin_allowed: bool = False,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        query = f"""
        INSERT INTO {self.schema}.accounts (
            user_id,
            cash_balance,
            base_currency,
            margin_allowed,
            created_at,
            updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (user_id) DO UPDATE SET
            cash_balance = EXCLUDED.cash_balance,
            margin_allowed = EXCLUDED.margin_allowed,
            updated_at = EXCLUDED.updated_at
        """
        now = datetime.now(timezone.utc)
        created = created_at or now
        updated = updated_at or now
        async with self.pool.acquire() as conn:  # type: ignore[attr-defined]
            await conn.execute(query, user_id, starting_balance, currency, margin_allowed, created, updated)


__all__ = [
    "AccountRepository",
    "PostgresAccountRepository",
    "PostgresUserRepository",
    "UserRepository",
]
