import json
from datetime import datetime, timezone

import pytest

from market_data.models import DealerQuoteEvent, OrderBookLevel, OrderBookSnapshot, TickEvent
from market_data.persistence import (
    PostgresDealerQuoteRepository,
    PostgresOrderBookRepository,
    PostgresTickRepository,
)


class StubConnection:
    def __init__(self, recorder: list[tuple[str, tuple]]) -> None:
        self._recorder = recorder

    async def execute(self, query: str, *args: object) -> None:
        self._recorder.append((query.strip(), args))

    async def __aenter__(self) -> "StubConnection":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        return None


class StubPool:
    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple]] = []

    def acquire(self) -> StubConnection:
        return StubConnection(self.executions)


def test_postgres_tick_repository_persists_payload() -> None:
    pool = StubPool()
    repo = PostgresTickRepository(pool=pool, schema="md")
    event = TickEvent(
        instrument_id="EQ-1",
        timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        bid=99.5,
        ask=100.5,
        mid=100.0,
        liquidity_regime="HIGH",
        metadata={"spread_bps": 10},
    )

    asyncio_run(repo.persist_tick(event))

    assert len(pool.executions) == 1
    query, params = pool.executions[0]
    assert "INSERT INTO md.market_ticks" in query
    assert params[0] == "EQ-1"
    assert params[2] == pytest.approx(99.5)
    assert params[3] == pytest.approx(100.5)
    assert json.loads(params[6]) == {"spread_bps": 10}


def test_postgres_order_book_repository_serializes_levels() -> None:
    pool = StubPool()
    repo = PostgresOrderBookRepository(pool=pool, schema="md")
    snapshot = OrderBookSnapshot(
        instrument_id="EQ-BOOK",
        timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        bids=[
            OrderBookLevel(price=99.9, quantity=500),
            OrderBookLevel(price=99.8, quantity=300),
        ],
        asks=[
            OrderBookLevel(price=100.1, quantity=400),
            OrderBookLevel(price=100.2, quantity=200),
        ],
    )

    asyncio_run(repo.persist_order_book(snapshot))

    query, params = pool.executions[0]
    assert "INSERT INTO md.order_books" in query
    payload = json.loads(params[2])
    assert payload["bids"][0]["price"] == 99.9
    assert payload["asks"][1]["quantity"] == 200


def test_postgres_dealer_quote_repository_persists_quote() -> None:
    pool = StubPool()
    repo = PostgresDealerQuoteRepository(pool=pool, schema="md")
    quote = DealerQuoteEvent(
        instrument_id="SWAP-5Y",
        dealer_id="DEALER-A",
        timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        bid=0.0125,
        ask=0.0135,
        metadata={"tenor": "5Y"},
    )

    asyncio_run(repo.persist_dealer_quote(quote))

    query, params = pool.executions[0]
    assert "INSERT INTO md.market_ticks" in query
    assert params[0] == "SWAP-5Y"
    assert params[5] == "DEALER-A"
    assert pytest.approx(params[4], rel=1e-6) == 0.013


def asyncio_run(coro) -> None:
    import asyncio

    asyncio.run(coro)
