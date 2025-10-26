from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Iterator

import pytest

from tests.trading.in_memory import (
    InMemoryExecutionPublisher,
    InMemoryTradingUnitOfWork,
)
from trading.domain.exceptions import (
    InsufficientBalanceError,
    InsufficientPositionError,
)
from trading.domain.matching import MatchingEngine
from trading.domain.models import (
    LimitOrderRequest,
    ListedInstrumentBook,
    MarketOrderRequest,
    OrderRecord,
    OrderSide,
    OrderStatus,
)
from trading.services.order_service import OrderService

pytestmark = pytest.mark.integration

def build_book() -> ListedInstrumentBook:
    return ListedInstrumentBook(
        instrument_id="instr-abc",
        bids=[(99.5, 100), (99.0, 200)],
        asks=[(100.5, 150), (101.0, 100)],
        last_updated=datetime.now(tz=timezone.utc),
    )


def id_sequence() -> Iterator[str]:
    counter = 0
    while True:
        counter += 1
        yield f"order-{counter}"


@pytest.mark.asyncio
async def test_limit_buy_order_executes_and_updates_state() -> None:
    ids = id_sequence()

    def generate_id() -> str:
        return next(ids)

    publisher = InMemoryExecutionPublisher(published=[])
    service = OrderService(
        uow_factory=InMemoryTradingUnitOfWork,
        matching_engine=MatchingEngine(),
        execution_publisher=publisher,
        id_generator=generate_id,
        clock=lambda: datetime.now(tz=timezone.utc),
    )
    order_request = LimitOrderRequest(
        user_id="user-123",
        instrument_id="instr-abc",
        side=OrderSide.BUY,
        quantity=180,
        limit_price=101.0,
        time_in_force="GTC",
    )
    result = await service.submit(order_request, build_book())
    assert isinstance(result, OrderRecord)
    assert result.status is OrderStatus.FILLED
    assert result.filled_quantity == 180
    assert publisher.published, "execution should be published"
    execution = publisher.published[0]
    assert execution.quantity == 180
    assert execution.price == pytest.approx((150 * 100.5 + 30 * 101.0) / 180)


@pytest.mark.asyncio
async def test_sell_order_rejects_without_position() -> None:
    ids = id_sequence()
    service = OrderService(
        uow_factory=InMemoryTradingUnitOfWork,
        matching_engine=MatchingEngine(),
        execution_publisher=InMemoryExecutionPublisher(published=[]),
        id_generator=lambda: next(ids),
        clock=lambda: datetime.now(tz=timezone.utc),
    )
    order_request = LimitOrderRequest(
        user_id="user-123",
        instrument_id="instr-abc",
        side=OrderSide.SELL,
        quantity=10,
        limit_price=99.0,
        time_in_force="GTC",
    )
    with pytest.raises(InsufficientPositionError):
        await service.submit(order_request, build_book())


@pytest.mark.asyncio
async def test_market_buy_rejects_when_cash_insufficient() -> None:
    ids = id_sequence()
    publisher = InMemoryExecutionPublisher(published=[])

    class LowBalanceUoW(InMemoryTradingUnitOfWork):
        def __init__(self) -> None:
            super().__init__()
            snapshot = self.accounts.store["user-123"]
            self.accounts.store["user-123"] = snapshot.model_copy(update={"cash_balance": 100.0})

    service = OrderService(
        uow_factory=LowBalanceUoW,
        matching_engine=MatchingEngine(),
        execution_publisher=publisher,
        id_generator=lambda: next(ids),
        clock=lambda: datetime.now(tz=timezone.utc),
    )
    order_request = MarketOrderRequest(
        user_id="user-123",
        instrument_id="instr-abc",
        side=OrderSide.BUY,
        quantity=10,
    )
    with pytest.raises(InsufficientBalanceError):
        await service.submit(order_request, build_book())
