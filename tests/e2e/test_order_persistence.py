from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest

from auth.server import _prepare_schema
from auth.storage import PostgresAccountRepository, PostgresUserRepository
from trading.domain.matching import MatchingEngine
from trading.domain.models import ListedInstrumentBook, MarketOrderRequest, OrderSide, OrderStatus
from trading.infrastructure.uow import AsyncpgTradingUnitOfWork
from trading.services.order_service import OrderService

pytestmark = pytest.mark.e2e

if os.getenv("RUN_E2E_TESTS") != "1":
    pytest.skip("E2E tests require RUN_E2E_TESTS=1", allow_module_level=True)


@pytest.mark.asyncio
async def test_orders_and_balances_survive_schema_preparation() -> None:
    schema = f"order_test_{uuid4().hex}"
    pool = await asyncpg.create_pool(
        dsn=os.getenv(
            "E2E_POSTGRES_DSN",
            "postgresql://postgres:postgres@localhost:5432/marketdata",
        ),
        min_size=1,
        max_size=3,
        server_settings={"search_path": schema},
    )
    try:
        await _prepare_schema(pool, schema)
        users = PostgresUserRepository(pool=pool, schema=schema)
        accounts = PostgresAccountRepository(pool=pool, schema=schema)
        user = await users.create(email="persistence@example.com", password_hash="test-only")
        await accounts.create_account(user.id, Decimal("1000"), "USD")

        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        publisher = AsyncMock()
        service = OrderService(
            uow_factory=lambda: AsyncpgTradingUnitOfWork(pool=pool),
            matching_engine=MatchingEngine(),
            execution_publisher=publisher,
            id_generator=lambda: "persisted-order",
            clock=lambda: now,
        )
        book = ListedInstrumentBook(
            instrument_id="EQ-TEST", bids=[(99.0, 20)], asks=[(100.0, 20)],
            last_updated=now,
        )
        submitted = await service.submit(
            MarketOrderRequest(
                user_id=user.id, instrument_id="EQ-TEST", side=OrderSide.BUY, quantity=2,
            ),
            book,
        )
        assert submitted.status is OrderStatus.FILLED
        publisher.publish.assert_awaited_once()

        # Startup preparation must preserve data on existing database volumes.
        await _prepare_schema(pool, schema)
        async with AsyncpgTradingUnitOfWork(pool=pool) as uow:
            assert await uow.orders.get_order(submitted.order_id) == submitted
            account = await uow.accounts.get_account(user.id)
            position = await uow.positions.get_position(user.id, "EQ-TEST")
            assert account is not None and account.cash_balance == 800.0
            assert position is not None and position.quantity == 2
            assert position.average_price == 100.0

        # A later failure must roll back all database writes in the unit of work.
        publisher.publish.side_effect = RuntimeError("publisher unavailable")
        service._id_generator = lambda: "rolled-back-order"
        with pytest.raises(RuntimeError, match="publisher unavailable"):
            await service.submit(
                MarketOrderRequest(
                    user_id=user.id, instrument_id="EQ-TEST", side=OrderSide.BUY, quantity=1,
                ),
                book,
            )
        async with AsyncpgTradingUnitOfWork(pool=pool) as uow:
            assert await uow.orders.get_order("rolled-back-order") is None
            account = await uow.accounts.get_account(user.id)
            position = await uow.positions.get_position(user.id, "EQ-TEST")
            assert account is not None and account.cash_balance == 800.0
            assert position is not None and position.quantity == 2
    finally:
        async with pool.acquire() as connection:
            await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await pool.close()
