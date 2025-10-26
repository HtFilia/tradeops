from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Awaitable, Callable, Iterable, Mapping, Sequence

import asyncpg
from redis.asyncio import Redis
import uvicorn

from market_data.configuration import (
    DealerQuoteSettings,
    InstrumentConfig,
    MarketDataConfig,
    OrderBookSettings,
    ScenarioSettings,
    PRESET_SCENARIOS,
)
from market_data.persistence import (
    PostgresDealerQuoteRepository,
    PostgresOrderBookRepository,
    PostgresTickRepository,
)
from market_data.publisher import (
    RedisDealerQuotePublisher,
    RedisOrderBookPublisher,
    RedisTickPublisher,
)
from market_data.runner import MarketDataRunner
from market_data.service import MarketDataService, InstrumentFeed
from market_data.management_api import create_management_app
from common.logging import configure_structured_logging

logger = configure_structured_logging("market_data.app")


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


DEFAULT_INSTRUMENTS: Sequence[InstrumentConfig] = (
    InstrumentConfig(
        instrument_id="EQ-ACME",
        instrument_type="EQUITY",
        start_price=100.0,
        drift=0.05,
        volatility=0.2,
        step_seconds=1.0,
        tick_size=0.01,
        update_interval_ms=500,
        seed=1,
        liquidity_regime="HIGH",
        order_book=OrderBookSettings(
            levels=3,
            tick_size=0.01,
            base_quantity=500.0,
            quantity_decay=0.6,
        ),
    ),
    InstrumentConfig(
        instrument_id="BOND-5Y",
        instrument_type="RATE",
        start_price=0.015,
        mean_reversion=0.6,
        long_run_mean=0.018,
        volatility=0.0008,
        step_seconds=1.0,
        tick_size=0.0001,
        update_interval_ms=1000,
        seed=2,
        liquidity_regime="MEDIUM",
        tenor="5Y",
        curve_points={"1Y": 0.012, "3Y": 0.014, "5Y": 0.016},
        dv01_per_million=540.0,
        dealer_quotes=DealerQuoteSettings(
            dealers=("DEALER-A", "DEALER-B"),
            base_spread=0.0004,
            spread_volatility=0.0001,
        ),
    ),
    InstrumentConfig(
        instrument_id="FUT-ES",
        instrument_type="FUTURE",
        start_price=4300.0,
        drift=0.01,
        volatility=0.18,
        step_seconds=1.0,
        tick_size=0.25,
        update_interval_ms=250,
        seed=3,
        liquidity_regime="HIGH",
        contract_month="2024-06",
        tick_value=12.5,
        multiplier=50,
    ),
)


def _build_instrument_config(payload: dict) -> InstrumentConfig:
    data = dict(payload)
    if "order_book" in data and data["order_book"] is not None:
        data["order_book"] = OrderBookSettings(**data["order_book"])
    if "dealer_quotes" in data and data["dealer_quotes"] is not None:
        data["dealer_quotes"] = DealerQuoteSettings(**data["dealer_quotes"])
    if "scenario" in data and data["scenario"] is not None:
        data["scenario"] = ScenarioSettings(**data["scenario"])
    return InstrumentConfig(**data)


def load_instrument_configs() -> Iterable[InstrumentConfig]:
    raw = os.getenv("MARKET_DATA_INSTRUMENTS")
    if not raw:
        return DEFAULT_INSTRUMENTS
    try:
        entries = json.loads(raw)
        if not isinstance(entries, list):
            raise ValueError("MARKET_DATA_INSTRUMENTS must be a JSON list of instrument configs")
    except json.JSONDecodeError as exc:  # pragma: no cover - hard to hit deterministically
        raise ValueError("Invalid JSON for MARKET_DATA_INSTRUMENTS") from exc
    return [_build_instrument_config(entry) for entry in entries]


async def create_market_data_service() -> tuple[
    MarketDataService,
    Sequence[InstrumentFeed],
    Mapping[str, ScenarioSettings],
    Callable[[], Awaitable[None]],
]:
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    postgres_dsn = os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@postgres:5432/marketdata")
    postgres_schema = os.getenv("POSTGRES_SCHEMA", "public")

    redis = Redis.from_url(redis_url)
    pool = await asyncpg.create_pool(dsn=postgres_dsn, min_size=1, max_size=5)

    tick_stream = os.getenv("REDIS_TICK_STREAM", "marketdata_ticks")
    order_book_stream = os.getenv("REDIS_ORDER_BOOK_STREAM", "marketdata_order_books")
    dealer_quote_stream = os.getenv("REDIS_DEALER_QUOTE_STREAM", "marketdata_dealer_quotes")

    instruments = list(load_instrument_configs())
    logger.info(
        "Loaded instrument configs",
        extra={
            "event": "market_data.instrument_configs_loaded",
            "context": {"instrument_count": len(instruments)},
        },
    )
    for inst in instruments:
        logger.debug(
            "Instrument configuration",
            extra={
                "event": "market_data.instrument_config_parsed",
                "context": {"instrument": asdict(inst)},
            },
        )

    feeds = MarketDataConfig(instruments=instruments).build_feeds()
    scenarios = PRESET_SCENARIOS

    service = MarketDataService(
        feeds=feeds,
        publisher=RedisTickPublisher(redis=redis, stream_name=tick_stream),
        repository=PostgresTickRepository(pool=pool, schema=postgres_schema),
        clock=SystemClock(),
        order_book_publisher=RedisOrderBookPublisher(redis=redis, stream_name=order_book_stream),
        order_book_repository=PostgresOrderBookRepository(pool=pool, schema=postgres_schema),
        dealer_quote_publisher=RedisDealerQuotePublisher(redis=redis, stream_name=dealer_quote_stream),
        dealer_quote_repository=PostgresDealerQuoteRepository(pool=pool, schema=postgres_schema),
    )

    async def cleanup() -> None:
        logger.info(
            "Shutting down market data service",
            extra={"event": "market_data.shutdown"},
        )
        await pool.close()
        await redis.aclose()

    return service, feeds, scenarios, cleanup


async def run() -> None:
    interval_seconds = float(os.getenv("MARKET_DATA_INTERVAL_SECONDS", "0.2"))
    log_level = os.getenv("MARKET_DATA_LOG_LEVEL")
    if log_level:
        logger.setLevel(log_level.upper())
    service, feeds, scenarios, cleanup = await create_market_data_service()
    cors_origins_raw = os.getenv("MARKET_DATA_CORS_ORIGINS")
    if cors_origins_raw:
        cors_origins = [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]
    else:
        cors_origins = ["http://localhost:5173"]

    management_app = create_management_app(
        service=service,
        feeds=feeds,
        scenarios=scenarios,
        cors_origins=cors_origins,
    )

    http_host = os.getenv("MARKET_DATA_HTTP_HOST", "0.0.0.0")
    http_port = int(os.getenv("MARKET_DATA_HTTP_PORT", "8080"))
    server_config = uvicorn.Config(
        app=management_app,
        host=http_host,
        port=http_port,
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(server_config)

    runner = MarketDataRunner(service=service, interval_seconds=interval_seconds)

    runner_task = asyncio.create_task(runner.run())
    server_task = asyncio.create_task(server.serve())

    try:
        done, _ = await asyncio.wait(
            {runner_task, server_task},
            return_when=asyncio.FIRST_EXCEPTION,
        )
        for task in done:
            task.result()
    except asyncio.CancelledError:
        raise
    except KeyboardInterrupt:
        logger.info("Received shutdown signal.")
    finally:
        server.should_exit = True
        for task in (runner_task, server_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(runner_task, server_task, return_exceptions=True)
        await cleanup()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
