from __future__ import annotations

import os
from datetime import timedelta
from typing import Sequence
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from redis.asyncio import Redis

from auth.app import create_auth_app
from auth.configuration import AuthConfig
from auth.session import RedisSessionStore
from auth.storage import PostgresAccountRepository, PostgresUserRepository
from auth.security import Argon2PasswordHasher
from common.logging import configure_structured_logging

logger = configure_structured_logging("auth.server")


class _PoolProxy:
    """Deferred asyncpg pool proxy to satisfy repository interfaces before startup."""

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None

    def set_pool(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    def acquire(self):
        if self._pool is None:
            raise RuntimeError("Database pool not initialised")
        return self._pool.acquire()


def _parse_origins(raw: str | None, default: Sequence[str]) -> list[str]:
    if raw is None:
        return list(default)
    candidates = [part.strip() for part in raw.split(",") if part.strip()]
    return candidates or list(default)


def create_default_app() -> FastAPI:
    env = os.environ
    config = AuthConfig.from_env(env)
    postgres_dsn = env.get("AUTH_POSTGRES_DSN", "postgresql://postgres:postgres@postgres:5432/marketdata")
    postgres_schema = env.get("AUTH_POSTGRES_SCHEMA", "public")
    redis_url = env.get("AUTH_REDIS_URL", "redis://redis:6379/0")
    cors_origins = _parse_origins(env.get("AUTH_CORS_ORIGINS"), ["http://localhost:5173"])

    pool_proxy = _PoolProxy()
    user_repository = PostgresUserRepository(pool=pool_proxy, schema=postgres_schema)
    account_repository = PostgresAccountRepository(pool=pool_proxy, schema=postgres_schema)
    redis_client = Redis.from_url(redis_url)
    session_store = RedisSessionStore(
        redis=redis_client,
        ttl=timedelta(minutes=config.session_ttl_minutes),
    )

    app = create_auth_app(
        user_repository=user_repository,
        account_repository=account_repository,
        session_store=session_store,
        config=config,
        cors_origins=cors_origins,
    )

    password_hasher = Argon2PasswordHasher()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        pool = await asyncpg.create_pool(dsn=postgres_dsn)
        pool_proxy.set_pool(pool)
        await _prepare_schema(pool, postgres_schema)
        await _ensure_default_user(
            user_repository=user_repository,
            account_repository=account_repository,
            password_hasher=password_hasher,
            config=config,
            email=env.get("AUTH_DEFAULT_USER_EMAIL", "demo@example.com"),
            password=env.get("AUTH_DEFAULT_USER_PASSWORD", "demo"),
        )
        try:
            yield
        finally:
            if pool_proxy._pool is not None:
                await pool_proxy._pool.close()
            await redis_client.aclose()

    app.router.lifespan_context = lifespan

    return app


async def _ensure_default_user(
    *,
    user_repository: PostgresUserRepository,
    account_repository: PostgresAccountRepository,
    password_hasher: Argon2PasswordHasher,
    config: AuthConfig,
    email: str,
    password: str,
) -> None:
    existing = await user_repository.get_by_email(email)
    if existing is not None:
        logger.info("Default demo user already exists", extra={"event": "auth.demo_user.exists"})
        return

    password_hash = password_hasher.hash(password)
    user = await user_repository.create(email=email, password_hash=password_hash)
    await account_repository.create_account(
        user_id=user.id,
        starting_balance=config.starting_balance,
        currency=config.base_currency,
        margin_allowed=False,
    )
    logger.info(
        "Seeded demo user",
        extra={"event": "auth.demo_user.created", "context": {"email": email}},
    )


async def _prepare_schema(pool: asyncpg.Pool, schema: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        await conn.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {schema}.users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {schema}.accounts (
                user_id UUID PRIMARY KEY REFERENCES {schema}.users (id) ON DELETE CASCADE,
                cash_balance NUMERIC(18, 4) NOT NULL,
                base_currency TEXT NOT NULL,
                margin_allowed BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {schema}.positions (
                user_id UUID NOT NULL REFERENCES {schema}.users (id) ON DELETE CASCADE,
                instrument_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                average_price NUMERIC(18, 6) NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (user_id, instrument_id)
            )
            """
        )


__all__ = ["create_default_app"]
