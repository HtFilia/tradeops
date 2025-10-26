from __future__ import annotations

from dataclasses import asdict
from typing import Mapping, Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from market_data.configuration import ScenarioSettings
from market_data.models import TickEvent
from market_data.service import InstrumentFeed, MarketDataService


def _serialize_tick(tick: TickEvent | None) -> dict[str, float | str] | None:
    if tick is None:
        return None
    return {
        "timestamp": tick.timestamp.isoformat(),
        "bid": tick.bid,
        "ask": tick.ask,
        "mid": tick.mid,
        "liquidity_regime": tick.liquidity_regime,
    }


def create_management_app(
    service: MarketDataService,
    feeds: Sequence[InstrumentFeed],
    scenarios: Mapping[str, ScenarioSettings],
    *,
    cors_origins: Sequence[str] | None = None,
) -> FastAPI:
    app = FastAPI(title="Market Data Management API", version="0.1.0")

    origins = list(cors_origins or ["http://localhost:5173"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    @app.get("/health")
    async def health() -> dict[str, object]:
        instrument_payload = {}
        for feed in feeds:
            last_tick = service.last_tick(feed.instrument_id) if hasattr(service, "last_tick") else None
            instrument_payload[feed.instrument_id] = {
                "last_tick": _serialize_tick(last_tick),
                "liquidity_regime": feed.liquidity_regime,
            }
        return {
            "status": "ok",
            "instruments": instrument_payload,
        }

    @app.get("/metrics")
    async def metrics() -> dict[str, object]:
        instrument_metrics = {}
        for feed in feeds:
            instrument_metrics[feed.instrument_id] = {
                "update_interval_seconds": feed.update_interval.total_seconds(),
                "tick_size": feed.tick_size,
                "liquidity_regime": feed.liquidity_regime,
            }
        return {
            "instruments": instrument_metrics,
            "scenarios": {name: asdict(settings) for name, settings in scenarios.items()},
        }

    return app


__all__ = ["create_management_app"]
