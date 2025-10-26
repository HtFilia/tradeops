from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Iterable, Protocol, Sequence

from market_data.models import DealerQuoteEvent, OrderBookSnapshot, TickEvent
from market_data.retry import retry_async


class Clock(Protocol):
    def now(self) -> datetime:
        """Return the current UTC timestamp."""


class TickPublisher(Protocol):
    async def publish_tick(self, event: TickEvent) -> None:
        """Publish a tick event onto the streaming bus."""


class TickRepository(Protocol):
    async def persist_tick(self, event: TickEvent) -> None:
        """Persist a tick event to durable storage."""


class PriceGenerator(Protocol):
    instrument_id: str

    def next_value(self) -> float:
        """Produce the next simulated mark."""


class OrderBookGenerator(Protocol):
    instrument_id: str

    def build(self, mid_price: float, timestamp: datetime) -> OrderBookSnapshot:
        """Construct a book snapshot for the current mid price."""


class DealerQuoteSource(Protocol):
    instrument_id: str

    def generate(self, mid_rate: float, timestamp: datetime) -> Iterable[DealerQuoteEvent]:
        """Produce dealer quotes for the instrument."""


class OrderBookPublisher(Protocol):
    async def publish_order_book(self, snapshot: OrderBookSnapshot) -> None:
        """Publish an order book snapshot onto the streaming bus."""


class DealerQuotePublisher(Protocol):
    async def publish_dealer_quote(self, quote: DealerQuoteEvent) -> None:
        """Publish a dealer quote event onto the streaming bus."""


class OrderBookRepository(Protocol):
    async def persist_order_book(self, snapshot: OrderBookSnapshot) -> None:
        """Persist an order book snapshot."""


class DealerQuoteRepository(Protocol):
    async def persist_dealer_quote(self, quote: DealerQuoteEvent) -> None:
        """Persist a dealer quote event."""


MetadataFactory = Callable[[float], dict[str, Any]]


@dataclass
class InstrumentFeed:
    instrument_id: str
    simulator: PriceGenerator
    tick_size: float
    liquidity_regime: str
    update_interval: timedelta = field(default=timedelta(seconds=1))
    metadata_factory: MetadataFactory | None = None
    order_book_generator: OrderBookGenerator | None = None
    dealer_quote_generator: DealerQuoteSource | None = None

    def __post_init__(self) -> None:
        if self.tick_size <= 0:
            raise ValueError("tick_size must be strictly positive")
        if self.update_interval.total_seconds() <= 0:
            raise ValueError("update_interval must be positive")
        if self.instrument_id != self.simulator.instrument_id:
            raise ValueError("Feed instrument id must match simulator instrument id")

    def next_tick(self, timestamp: datetime) -> TickEvent:
        """Generate the next tick event for this instrument."""
        mid = self.simulator.next_value()
        half_spread = self.tick_size / 2.0
        bid = mid - half_spread
        ask = mid + half_spread
        metadata = self.metadata_factory(mid) if self.metadata_factory else None
        return TickEvent(
            instrument_id=self.instrument_id,
            timestamp=timestamp,
            bid=bid,
            ask=ask,
            mid=mid,
            liquidity_regime=self.liquidity_regime,
            metadata=metadata,
        )


@dataclass
class MarketDataService:
    feeds: Sequence[InstrumentFeed]
    publisher: TickPublisher
    repository: TickRepository
    clock: Clock
    order_book_publisher: OrderBookPublisher | None = None
    dealer_quote_publisher: DealerQuotePublisher | None = None
    order_book_repository: OrderBookRepository | None = None
    dealer_quote_repository: DealerQuoteRepository | None = None
    retry_attempts: int = 3
    retry_backoff_seconds: float = 0.05
    sleep_provider: Callable[[float], Awaitable[None]] = field(default=asyncio.sleep, repr=False)
    _last_emitted: dict[str, TickEvent] = field(default_factory=dict, init=False)
    _next_emission: dict[str, datetime] = field(default_factory=dict, init=False)

    async def pump_once(self) -> None:
        """Generate ticks for all feeds and dispatch them downstream."""
        timestamp = self.clock.now()
        emissions: list[tuple[InstrumentFeed, TickEvent]] = []

        for feed in self.feeds:
            next_due = self._next_emission.get(feed.instrument_id)
            if next_due is not None and timestamp < next_due:
                continue

            tick = feed.next_tick(timestamp)
            emissions.append((feed, tick))
            self._next_emission[feed.instrument_id] = timestamp + feed.update_interval

        for feed, event in emissions:
            await retry_async(
                self.repository.persist_tick,
                event,
                attempts=self.retry_attempts,
                base_delay=self.retry_backoff_seconds,
                sleep=self.sleep_provider,
            )
            await retry_async(
                self.publisher.publish_tick,
                event,
                attempts=self.retry_attempts,
                base_delay=self.retry_backoff_seconds,
                sleep=self.sleep_provider,
            )
            self._last_emitted[event.instrument_id] = event

            if feed.order_book_generator is not None:
                snapshot = feed.order_book_generator.build(event.mid, timestamp)
                if self.order_book_repository is not None:
                    await retry_async(
                        self.order_book_repository.persist_order_book,
                        snapshot,
                        attempts=self.retry_attempts,
                        base_delay=self.retry_backoff_seconds,
                        sleep=self.sleep_provider,
                    )
                if self.order_book_publisher is not None:
                    await retry_async(
                        self.order_book_publisher.publish_order_book,
                        snapshot,
                        attempts=self.retry_attempts,
                        base_delay=self.retry_backoff_seconds,
                        sleep=self.sleep_provider,
                    )

            if feed.dealer_quote_generator is not None:
                quotes = list(feed.dealer_quote_generator.generate(event.mid, timestamp))
                if quotes:
                    if self.dealer_quote_repository is not None:
                        for quote in quotes:
                            await retry_async(
                                self.dealer_quote_repository.persist_dealer_quote,
                                quote,
                                attempts=self.retry_attempts,
                                base_delay=self.retry_backoff_seconds,
                                sleep=self.sleep_provider,
                            )
                    if self.dealer_quote_publisher is not None:
                        for quote in quotes:
                            await retry_async(
                                self.dealer_quote_publisher.publish_dealer_quote,
                                quote,
                                attempts=self.retry_attempts,
                                base_delay=self.retry_backoff_seconds,
                                sleep=self.sleep_provider,
                            )

    def last_tick(self, instrument_id: str) -> TickEvent | None:
        """Return the last emitted tick for the given instrument if available."""
        return self._last_emitted.get(instrument_id)
