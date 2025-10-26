from __future__ import annotations

import json
from datetime import datetime, timezone

from redis.asyncio import Redis

from trading.domain.exceptions import InstrumentNotFoundError
from trading.domain.models import ListedInstrumentBook
from trading.ports.market_data import MarketDataGateway


class RedisMarketDataGateway(MarketDataGateway):
    def __init__(self, *, client: Redis, book_prefix: str = "marketdata:book") -> None:
        self._client = client
        self._book_prefix = book_prefix

    async def get_order_book(self, instrument_id: str) -> ListedInstrumentBook:
        key = f"{self._book_prefix}:{instrument_id}"
        data = await self._client.hgetall(key)
        if not data:
            raise InstrumentNotFoundError(f"instrument {instrument_id} not found")

        def _decode(field: bytes) -> str:
            value = data.get(field)
            if value is None:
                raise InstrumentNotFoundError(f"missing field {field.decode()} for instrument {instrument_id}")
            return value.decode()

        bids = json.loads(_decode(b"bids"))
        asks = json.loads(_decode(b"asks"))
        timestamp_str = _decode(b"last_updated")
        last_updated = datetime.fromisoformat(timestamp_str)
        if last_updated.tzinfo is None:
            last_updated = last_updated.replace(tzinfo=timezone.utc)

        return ListedInstrumentBook(
            instrument_id=instrument_id,
            bids=[(float(price), int(quantity)) for price, quantity in bids],
            asks=[(float(price), int(quantity)) for price, quantity in asks],
            last_updated=last_updated,
        )
