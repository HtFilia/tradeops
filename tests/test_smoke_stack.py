import os
import time

import pytest

pytest.importorskip("asyncpg")
pytest.importorskip("redis.asyncio")

import asyncpg  # type: ignore  # noqa: E402
from redis.asyncio import Redis  # type: ignore  # noqa: E402


SMOKE_ENV = "MARKET_DATA_SMOKE"


def required_env(name: str, default: str) -> str:
    return os.getenv(name, default)


@pytest.mark.skipif(not os.getenv(SMOKE_ENV), reason="market data smoke tests require running docker stack")
@pytest.mark.asyncio
async def test_market_data_stack_streams_and_persists() -> None:
    redis_url = required_env("MARKET_DATA_REDIS_URL", "redis://localhost:6379/0")
    postgres_dsn = required_env(
        "MARKET_DATA_POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/marketdata"
    )
    tick_stream = required_env("MARKET_DATA_TICK_STREAM", "marketdata_ticks")

    redis = Redis.from_url(redis_url)
    pool = await asyncpg.create_pool(dsn=postgres_dsn, min_size=1, max_size=2)

    try:
        # Nudge the stream to ensure it exists and read a few entries
        start_time = time.time()
        entries = []
        while time.time() - start_time < 10 and not entries:
            entries = await redis.xread({tick_stream: "0-0"}, block=1000)

        assert entries, "expected ticks to be published onto Redis stream"

        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT COUNT(*) AS cnt FROM public.market_ticks")
            assert row["cnt"] > 0, "expected persisted ticks in Postgres"
    finally:
        await redis.close()
        await pool.close()
