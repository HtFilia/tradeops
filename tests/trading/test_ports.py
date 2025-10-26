import asyncio
from datetime import datetime, timezone

import pytest
from tests.trading.in_memory import (
    InMemoryAccountsRepository,
    InMemoryExecutionPublisher,
    InMemoryOrdersRepository,
    InMemoryPositionsRepository,
    InMemoryTradingUnitOfWork,
)
from trading.domain.models import (
    OrderRecord,
    OrderSide,
    OrderStatus,
    OrderType,
)
from trading.ports.repositories import TradingUnitOfWork


@pytest.mark.asyncio
async def test_unit_of_work_runtime_checkable() -> None:
    uow = InMemoryTradingUnitOfWork()
    assert isinstance(uow, TradingUnitOfWork)
    async with uow as scoped:
        assert scoped.orders is uow.orders
    assert uow._committed is True


@pytest.mark.asyncio
async def test_orders_repository_contract() -> None:
    repository = InMemoryOrdersRepository(store={})
    now = datetime.now(tz=timezone.utc)
    order = OrderRecord(
        order_id="order-1",
        user_id="user-123",
        instrument_id="instr-1",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        filled_quantity=0,
        limit_price=100.25,
        status=OrderStatus.NEW,
        time_in_force="GTC",
        created_at=now,
        updated_at=now,
    )
    created = await repository.create_order(order)
    assert created == order
    fetched = await repository.get_order(order.order_id)
    assert fetched == order
    updated = await repository.update_order(order)
    assert updated == order
