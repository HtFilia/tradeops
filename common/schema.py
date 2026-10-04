"""Additive startup migrations; serialized across auth and trading processes."""

import re
import asyncpg


async def prepare_schema(pool: asyncpg.Pool, schema: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        raise ValueError("Invalid database schema identifier")
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(731204)")
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

        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {schema}.orders (
                order_id TEXT PRIMARY KEY,
                user_id UUID NOT NULL REFERENCES {schema}.users (id) ON DELETE CASCADE,
                instrument_id TEXT NOT NULL,
                side TEXT NOT NULL,
                order_type TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                filled_quantity INTEGER NOT NULL,
                limit_price DOUBLE PRECISION,
                average_price DOUBLE PRECISION,
                status TEXT NOT NULL,
                time_in_force TEXT,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """
        )

        await conn.execute(
            f"ALTER TABLE {schema}.users ADD COLUMN IF NOT EXISTS principal_kind TEXT NOT NULL DEFAULT 'registered'"
        )
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {schema}.demo_guests (
                user_id UUID PRIMARY KEY REFERENCES {schema}.users(id) ON DELETE CASCADE,
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS demo_guests_expiry ON {schema}.demo_guests(expires_at);
            CREATE TABLE IF NOT EXISTS {schema}.demo_cases (
                user_id UUID PRIMARY KEY REFERENCES {schema}.demo_guests(user_id) ON DELETE CASCADE,
                generation UUID NOT NULL, case_id TEXT NOT NULL,
                submissions INTEGER NOT NULL DEFAULT 0, resets INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS {schema}.demo_receipts (
                receipt_id UUID PRIMARY KEY, user_id UUID NOT NULL REFERENCES {schema}.demo_guests(user_id) ON DELETE CASCADE,
                generation UUID NOT NULL, idempotency_key UUID NOT NULL, payload_hash TEXT NOT NULL,
                order_id TEXT REFERENCES {schema}.orders(order_id) ON DELETE CASCADE,
                detail JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(user_id, generation, idempotency_key)
            );
            CREATE INDEX IF NOT EXISTS demo_receipts_owner ON {schema}.demo_receipts(user_id, created_at DESC, receipt_id);
        """)
