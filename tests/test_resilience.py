import asyncio
from datetime import datetime, timezone

import pytest

from market_data.models import TickEvent
from market_data.service import InstrumentFeed, MarketDataService
from market_data.simulation.equity import GeometricBrownianMotionSimulator


class FlakyPublisher:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.events: list[TickEvent] = []

    async def publish_tick(self, event: TickEvent) -> None:
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError("publish failure")
        self.events.append(event)


class FlakyRepository:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.events: list[TickEvent] = []

    async def persist_tick(self, event: TickEvent) -> None:
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError("persist failure")
        self.events.append(event)


class NoopPublisher:
    async def publish_order_book(self, snapshot) -> None:  # pragma: no cover - placeholder
        return None


class NoopRepository:
    async def persist_order_book(self, snapshot) -> None:  # pragma: no cover - placeholder
        return None


async def no_sleep(_: float) -> None:
    return None


def build_feed() -> InstrumentFeed:
    simulator = GeometricBrownianMotionSimulator(
        instrument_id="EQ-FLAKY",
        start_price=100.0,
        drift=0.0,
        volatility=0.2,
        step_seconds=1.0,
        seed=7,
    )
    return InstrumentFeed(
        instrument_id="EQ-FLAKY",
        simulator=simulator,
        tick_size=0.01,
        liquidity_regime="MEDIUM",
    )


def test_market_data_service_retries_on_transient_failures() -> None:
    feed = build_feed()
    publisher = FlakyPublisher(failures=1)
    repository = FlakyRepository(failures=2)
    clock = lambda: datetime(2024, 1, 1, tzinfo=timezone.utc)

    class StaticClock:
        def now(self):
            return clock()

    service = MarketDataService(
        feeds=[feed],
        publisher=publisher,
        repository=repository,
        clock=StaticClock(),
        sleep_provider=no_sleep,
    )

    asyncio.run(service.pump_once())

    assert len(repository.events) == 1
    assert len(publisher.events) == 1


def test_market_data_service_raises_after_max_retries_exhausted() -> None:
    feed = build_feed()
    repository = FlakyRepository(failures=5)

    class StaticClock:
        def now(self):
            return datetime(2024, 1, 1, tzinfo=timezone.utc)

    service = MarketDataService(
        feeds=[feed],
        publisher=FlakyPublisher(failures=0),
        repository=repository,
        clock=StaticClock(),
        sleep_provider=no_sleep,
        retry_attempts=2,
    )

    with pytest.raises(RuntimeError):
        asyncio.run(service.pump_once())
