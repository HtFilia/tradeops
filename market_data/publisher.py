from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

from market_data.models import DealerQuoteEvent, OrderBookSnapshot, TickEvent

if TYPE_CHECKING:
    from redis.asyncio import Redis
else:  # pragma: no cover - when redis is unavailable at runtime
    Redis = Any  # type: ignore


def _serialize(event: Any) -> str:
    if hasattr(event, "model_dump_json"):
        return event.model_dump_json()
    return json.dumps(event.model_dump())


class RedisTickPublisher:
    """Publish tick events onto a Redis Stream."""

    def __init__(self, redis: Redis, stream_name: str = "marketdata_stream") -> None:
        self._redis = redis
        self._stream_name = stream_name

    async def publish_tick(self, event: TickEvent) -> None:
        await self._redis.xadd(self._stream_name, {"payload": _serialize(event)})


class RedisOrderBookPublisher:
    """Publish order book snapshots onto a Redis Stream."""

    def __init__(
        self,
        redis: Redis,
        stream_name: str = "orderbook_stream",
        book_hash_prefix: str = "marketdata:book",
    ) -> None:
        self._redis = redis
        self._stream_name = stream_name
        self._book_hash_prefix = book_hash_prefix

    async def publish_order_book(self, snapshot: OrderBookSnapshot) -> None:
        payload = _serialize(snapshot)
        await self._redis.xadd(self._stream_name, {"payload": payload})

        key = f"{self._book_hash_prefix}:{snapshot.instrument_id}"
        bids = [(float(level.price), int(level.quantity)) for level in snapshot.bids]
        asks = [(float(level.price), int(level.quantity)) for level in snapshot.asks]
        await self._redis.hset(
            key,
            mapping={
                "bids": json.dumps(bids),
                "asks": json.dumps(asks),
                "last_updated": snapshot.timestamp.isoformat(),
            },
        )


class RedisDealerQuotePublisher:
    """Publish dealer quote events onto a Redis Stream."""

    def __init__(self, redis: Redis, stream_name: str = "dealerquote_stream") -> None:
        self._redis = redis
        self._stream_name = stream_name

    async def publish_dealer_quote(self, quote: DealerQuoteEvent) -> None:
        await self._redis.xadd(self._stream_name, {"payload": _serialize(quote)})


# Backwards compatibility alias for earlier nomenclature.
RedisStreamPublisher = RedisTickPublisher


__all__ = [
    "RedisDealerQuotePublisher",
    "RedisOrderBookPublisher",
    "RedisStreamPublisher",
    "RedisTickPublisher",
]
