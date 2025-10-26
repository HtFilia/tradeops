from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from trading.domain.exceptions import InstrumentNotFoundError
from trading.domain.models import ExecutionEvent, OrderSide
from trading.infrastructure.events import RedisExecutionPublisher
from trading.infrastructure.market_data import RedisMarketDataGateway


@pytest.mark.asyncio
async def test_redis_execution_publisher_serialises_event() -> None:
    client = AsyncMock()
    publisher = RedisExecutionPublisher(client=client, stream="execution_stream")
    event = ExecutionEvent(
        execution_id="exec-1",
        order_id="order-1",
        user_id="user-123",
        instrument_id="instr-abc",
        side=OrderSide.BUY,
        quantity=50,
        price=101.25,
        timestamp=datetime.now(tz=timezone.utc),
    )
    await publisher.publish(event)
    client.xadd.assert_awaited_once()
    args, kwargs = client.xadd.await_args
    assert args[0] == "execution_stream"
    payload = kwargs.get("fields") or args[1]
    assert isinstance(payload["payload"], str)


class FakeRedis:
    def __init__(self, payload: dict):
        self._payload = payload

    async def hgetall(self, key: str) -> dict:
        return self._payload.get(key, {})


@pytest.mark.asyncio
async def test_redis_market_data_gateway_parses_snapshot() -> None:
    timestamp = datetime.now(tz=timezone.utc).isoformat()
    payload = {
        "marketdata:book:instr-abc": {
            b"bids": b"[[100.5, 50]]",
            b"asks": b"[[101.0, 75]]",
            b"last_updated": timestamp.encode(),
        }
    }
    gateway = RedisMarketDataGateway(client=FakeRedis(payload))
    book = await gateway.get_order_book("instr-abc")
    assert book.best_bid == (100.5, 50)
    assert book.best_ask == (101.0, 75)


@pytest.mark.asyncio
async def test_redis_market_data_gateway_raises_when_missing() -> None:
    gateway = RedisMarketDataGateway(client=FakeRedis({}))
    with pytest.raises(InstrumentNotFoundError):
        await gateway.get_order_book("missing")
