from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from market_data.generators.dealer_quotes import DealerQuoteGenerator
from market_data.generators.order_book import LadderOrderBookGenerator, OrderBookDepthConfig
from market_data.models import DealerQuoteEvent, OrderBookSnapshot, TickEvent
from market_data.service import InstrumentFeed, MarketDataService
from market_data.simulation.equity import GeometricBrownianMotionSimulator


class FrozenClock:
    """Deterministic clock for predictable timestamps in tests."""

    def __init__(self, fixed_timestamp: datetime) -> None:
        self._timestamp = fixed_timestamp

    def now(self) -> datetime:
        return self._timestamp


class AdvancingClock:
    """Clock that can be manually advanced to simulate wall time progression."""

    def __init__(self, start: datetime) -> None:
        self._current = start

    def now(self) -> datetime:
        return self._current

    def advance(self, delta: timedelta) -> None:
        self._current += delta


class RecordingPublisher:
    def __init__(self) -> None:
        self.published_ticks: list[TickEvent] = []

    async def publish_tick(self, event: TickEvent) -> None:
        self.published_ticks.append(event)


class RecordingRepository:
    def __init__(self) -> None:
        self.persisted_ticks: list[TickEvent] = []

    async def persist_tick(self, event: TickEvent) -> None:
        self.persisted_ticks.append(event)


class RecordingOrderBookPublisher:
    def __init__(self) -> None:
        self.snapshots: list[OrderBookSnapshot] = []

    async def publish_order_book(self, snapshot: OrderBookSnapshot) -> None:
        self.snapshots.append(snapshot)


class RecordingDealerQuotePublisher:
    def __init__(self) -> None:
        self.quotes: list[DealerQuoteEvent] = []

    async def publish_dealer_quote(self, quote: DealerQuoteEvent) -> None:
        self.quotes.append(quote)


class RecordingOrderBookRepository:
    def __init__(self) -> None:
        self.snapshots: list[OrderBookSnapshot] = []

    async def persist_order_book(self, snapshot: OrderBookSnapshot) -> None:
        self.snapshots.append(snapshot)


class RecordingDealerQuoteRepository:
    def __init__(self) -> None:
        self.quotes: list[DealerQuoteEvent] = []

    async def persist_dealer_quote(self, quote: DealerQuoteEvent) -> None:
        self.quotes.append(quote)


@dataclass
class FeedConfig:
    instrument_id: str
    start_price: float
    liquidity_regime: str


def test_market_data_service_generates_and_broadcasts_ticks() -> None:
    feed_config = FeedConfig(
        instrument_id="EQ-XYZ",
        start_price=150.0,
        liquidity_regime="MEDIUM",
    )
    simulator = GeometricBrownianMotionSimulator(
        instrument_id=feed_config.instrument_id,
        start_price=feed_config.start_price,
        drift=0.0,
        volatility=0.1,
        step_seconds=1.0,
        seed=7,
    )
    feed = InstrumentFeed(
        instrument_id=feed_config.instrument_id,
        simulator=simulator,
        tick_size=0.01,
        liquidity_regime=feed_config.liquidity_regime,
    )

    publisher = RecordingPublisher()
    repository = RecordingRepository()
    clock = FrozenClock(datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc))

    service = MarketDataService(
        feeds=[feed],
        publisher=publisher,
        repository=repository,
        clock=clock,
    )

    asyncio.run(service.pump_once())

    assert len(publisher.published_ticks) == 1
    assert len(repository.persisted_ticks) == 1

    published_tick = publisher.published_ticks[0]
    persisted_tick = repository.persisted_ticks[0]

    assert published_tick == persisted_tick
    assert published_tick.instrument_id == feed_config.instrument_id
    assert published_tick.timestamp == clock.now()
    assert pytest.approx(published_tick.mid, rel=1e-6) == published_tick.mid
    assert published_tick.bid < published_tick.ask
    assert published_tick.liquidity_regime == feed_config.liquidity_regime


def test_market_data_service_respects_feed_intervals() -> None:
    clock = AdvancingClock(datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc))

    fast_simulator = GeometricBrownianMotionSimulator(
        instrument_id="EQ-FAST",
        start_price=100.0,
        drift=0.0,
        volatility=0.1,
        step_seconds=1.0,
        seed=1,
    )
    slow_simulator = GeometricBrownianMotionSimulator(
        instrument_id="EQ-SLOW",
        start_price=200.0,
        drift=0.0,
        volatility=0.1,
        step_seconds=1.0,
        seed=2,
    )

    fast_feed = InstrumentFeed(
        instrument_id="EQ-FAST",
        simulator=fast_simulator,
        tick_size=0.01,
        liquidity_regime="HIGH",
        update_interval=timedelta(seconds=1),
    )
    slow_feed = InstrumentFeed(
        instrument_id="EQ-SLOW",
        simulator=slow_simulator,
        tick_size=0.05,
        liquidity_regime="LOW",
        update_interval=timedelta(seconds=2),
    )

    publisher = RecordingPublisher()
    repository = RecordingRepository()
    service = MarketDataService(
        feeds=[fast_feed, slow_feed],
        publisher=publisher,
        repository=repository,
        clock=clock,
    )

    # Initial pump emits both.
    asyncio.run(service.pump_once())
    assert {tick.instrument_id for tick in publisher.published_ticks} == {"EQ-FAST", "EQ-SLOW"}


def test_market_data_service_emits_books_and_quotes() -> None:
    clock = FrozenClock(datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc))
    simulator = GeometricBrownianMotionSimulator(
        instrument_id="EQ-L2",
        start_price=120.0,
        drift=0.0,
        volatility=0.15,
        step_seconds=1.0,
        seed=11,
    )

    order_book_generator = LadderOrderBookGenerator(
        instrument_id="EQ-L2",
        config=OrderBookDepthConfig(
            levels=2,
            tick_size=0.01,
            base_quantity=1000,
            quantity_decay=0.5,
        ),
        seed=5,
    )
    dealer_quote_generator = DealerQuoteGenerator(
        instrument_id="EQ-L2",
        dealers=["DEALER-A"],
        base_spread=0.5,
        spread_volatility=0.0,
        seed=9,
    )

    feed = InstrumentFeed(
        instrument_id="EQ-L2",
        simulator=simulator,
        tick_size=0.02,
        liquidity_regime="MEDIUM",
        order_book_generator=order_book_generator,
        dealer_quote_generator=dealer_quote_generator,
    )

    tick_publisher = RecordingPublisher()
    tick_repository = RecordingRepository()
    book_publisher = RecordingOrderBookPublisher()
    book_repository = RecordingOrderBookRepository()
    quote_publisher = RecordingDealerQuotePublisher()
    quote_repository = RecordingDealerQuoteRepository()

    service = MarketDataService(
        feeds=[feed],
        publisher=tick_publisher,
        repository=tick_repository,
        clock=clock,
        order_book_publisher=book_publisher,
        order_book_repository=book_repository,
        dealer_quote_publisher=quote_publisher,
        dealer_quote_repository=quote_repository,
    )

    asyncio.run(service.pump_once())

    assert len(book_publisher.snapshots) == 1
    assert len(book_repository.snapshots) == 1
    assert len(quote_publisher.quotes) == 1
    assert len(quote_repository.quotes) == 1
