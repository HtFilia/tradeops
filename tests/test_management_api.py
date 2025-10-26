from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi")

from market_data.configuration import PRESET_SCENARIOS, ScenarioSettings
from market_data.management_api import create_management_app
from market_data.models import TickEvent
from market_data.service import InstrumentFeed
from market_data.simulation.equity import GeometricBrownianMotionSimulator


class DummyService:
    def __init__(self, ticks: dict[str, TickEvent]) -> None:
        self._ticks = ticks

    def last_tick(self, instrument_id: str) -> TickEvent | None:
        return self._ticks.get(instrument_id)


def build_feed(instrument_id: str) -> InstrumentFeed:
    simulator = GeometricBrownianMotionSimulator(
        instrument_id=instrument_id,
        start_price=100.0,
        drift=0.0,
        volatility=0.2,
        step_seconds=1.0,
        seed=42,
    )
    return InstrumentFeed(
        instrument_id=instrument_id,
        simulator=simulator,
        tick_size=0.01,
        liquidity_regime="MEDIUM",
    )


@pytest.mark.asyncio
async def test_health_endpoint_reports_last_tick() -> None:
    tick = TickEvent(
        instrument_id="EQ-TEST",
        timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        bid=99.9,
        ask=100.1,
        mid=100.0,
        liquidity_regime="MEDIUM",
    )
    service = DummyService({"EQ-TEST": tick})
    app = create_management_app(service=service, feeds=[build_feed("EQ-TEST")], scenarios=PRESET_SCENARIOS)

    health_route = next(route for route in app.routes if getattr(route, "path", "") == "/health")
    payload = await health_route.endpoint()

    assert payload["status"] == "ok"
    assert payload["instruments"]["EQ-TEST"]["last_tick"]["mid"] == 100.0


@pytest.mark.asyncio
async def test_metrics_endpoint_includes_feed_configuration() -> None:
    feed = build_feed("EQ-METRIC")
    service = DummyService({})
    custom_scenarios = {"rally": ScenarioSettings(drift_shift=0.02, liquidity_regime="HIGH")}
    app = create_management_app(service=service, feeds=[feed], scenarios=custom_scenarios)

    metrics_route = next(route for route in app.routes if getattr(route, "path", "") == "/metrics")
    payload = await metrics_route.endpoint()

    instrument_metrics = payload["instruments"]["EQ-METRIC"]
    assert instrument_metrics["update_interval_seconds"] == pytest.approx(1.0)
    assert instrument_metrics["tick_size"] == 0.01
    assert payload["scenarios"]["rally"]["liquidity_regime"] == "HIGH"
