from __future__ import annotations

import json
from typing import Any, Protocol, TYPE_CHECKING

from market_data.models import DealerQuoteEvent, OrderBookSnapshot, TickEvent

if TYPE_CHECKING:
    import asyncpg


class SupportsAcquire(Protocol):
    def acquire(self) -> Any:
        ...


class PostgresTickRepository:
    """Async Postgres repository for persisting tick data."""

    def __init__(self, pool: SupportsAcquire, schema: str = "public") -> None:
        self._pool = pool
        self._schema = schema

    async def persist_tick(self, event: TickEvent) -> None:
        """Insert a tick event into the market_ticks table."""
        query = f"""
        INSERT INTO {self._schema}.market_ticks (
            instrument_id,
            timestamp,
            bid,
            ask,
            mid,
            dealer_id,
            metadata
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        """
        metadata: str | None = None
        if event.metadata is not None:
            metadata = json.dumps(event.metadata)

        async with self._pool.acquire() as conn:
            await conn.execute(
                query,
                event.instrument_id,
                event.timestamp,
                event.bid,
                event.ask,
                event.mid,
                None,
                metadata,
            )


class PostgresOrderBookRepository:
    """Persist ladder order book snapshots into Postgres."""

    def __init__(self, pool: SupportsAcquire, schema: str = "public") -> None:
        self._pool = pool
        self._schema = schema

    async def persist_order_book(self, snapshot: OrderBookSnapshot) -> None:
        payload = json.dumps(
            {
                "bids": [level.model_dump() for level in snapshot.bids],
                "asks": [level.model_dump() for level in snapshot.asks],
            }
        )
        query = f"""
        INSERT INTO {self._schema}.order_books (
            instrument_id,
            timestamp,
            levels
        ) VALUES ($1, $2, $3)
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                query,
                snapshot.instrument_id,
                snapshot.timestamp,
                payload,
            )


class PostgresDealerQuoteRepository:
    """Persist dealer quotes into market_ticks with dealer attribution."""

    def __init__(self, pool: SupportsAcquire, schema: str = "public") -> None:
        self._pool = pool
        self._schema = schema

    async def persist_dealer_quote(self, quote: DealerQuoteEvent) -> None:
        metadata: str | None = None
        if quote.metadata is not None:
            metadata = json.dumps(quote.metadata)

        mid = (quote.bid + quote.ask) / 2.0
        query = f"""
        INSERT INTO {self._schema}.market_ticks (
            instrument_id,
            timestamp,
            bid,
            ask,
            mid,
            dealer_id,
            metadata
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                query,
                quote.instrument_id,
                quote.timestamp,
                quote.bid,
                quote.ask,
                mid,
                quote.dealer_id,
                metadata,
            )


__all__ = [
    "PostgresDealerQuoteRepository",
    "PostgresOrderBookRepository",
    "PostgresTickRepository",
]
