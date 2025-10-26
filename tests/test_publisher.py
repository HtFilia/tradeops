import json
from datetime import datetime, timezone

from market_data.models import DealerQuoteEvent, OrderBookLevel, OrderBookSnapshot, TickEvent
from market_data.publisher import (
    RedisDealerQuotePublisher,
    RedisOrderBookPublisher,
    RedisTickPublisher,
)


class StubRedis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.hashes: dict[str, dict[str, str]] = {}

    async def xadd(self, stream: str, payload: dict[str, str]) -> None:
        self.calls.append((stream, payload))

    async def hset(self, key: str, mapping: dict[str, str]) -> None:
        self.hashes[key] = mapping


def make_tick() -> TickEvent:
    return TickEvent(
        instrument_id="EQ-1",
        timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        bid=99.5,
        ask=100.5,
        mid=100.0,
        liquidity_regime="HIGH",
    )


def make_snapshot() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        instrument_id="EQ-BOOK",
        timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        bids=[OrderBookLevel(price=99.9, quantity=500)],
        asks=[OrderBookLevel(price=100.1, quantity=400)],
    )


def make_quote() -> DealerQuoteEvent:
    return DealerQuoteEvent(
        instrument_id="SWAP-5Y",
        dealer_id="DEALER-A",
        timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        bid=0.0125,
        ask=0.013,
    )


def test_redis_tick_publisher_serializes_payload() -> None:
    redis = StubRedis()
    publisher = RedisTickPublisher(redis=redis, stream_name="ticks")

    tick = make_tick()
    asyncio_run(publisher.publish_tick(tick))

    stream, payload = redis.calls[0]
    assert stream == "ticks"
    assert json.loads(payload["payload"])["instrument_id"] == "EQ-1"


def test_redis_order_book_publisher_serializes_snapshot() -> None:
    redis = StubRedis()
    publisher = RedisOrderBookPublisher(redis=redis, stream_name="books")

    snapshot = make_snapshot()
    asyncio_run(publisher.publish_order_book(snapshot))

    stream, payload = redis.calls[0]
    data = json.loads(payload["payload"])
    assert data["bids"][0]["quantity"] == 500
    book_hash = redis.hashes["marketdata:book:EQ-BOOK"]
    assert json.loads(book_hash["bids"])[0][1] == 500


def test_redis_dealer_quote_publisher_serializes_quote() -> None:
    redis = StubRedis()
    publisher = RedisDealerQuotePublisher(redis=redis, stream_name="quotes")

    quote = make_quote()
    asyncio_run(publisher.publish_dealer_quote(quote))

    stream, payload = redis.calls[0]
    data = json.loads(payload["payload"])
    assert data["dealer_id"] == "DEALER-A"


def asyncio_run(coro):
    import asyncio

    asyncio.run(coro)
