from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from trading.domain.models import (
    AccountSnapshot,
    ExecutionEvent,
    OrderRecord,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionRecord,
)
from trading.ports.repositories import (
    AccountsRepository,
    ExecutionPublisher,
    OrdersRepository,
    PositionsRepository,
    TradingUnitOfWork,
)


@dataclass(slots=True)
class InMemoryOrdersRepository(OrdersRepository):
    store: dict[str, OrderRecord]

    async def create_order(self, order: OrderRecord) -> OrderRecord:
        self.store[order.order_id] = order
        return order

    async def get_order(self, order_id: str) -> OrderRecord | None:
        return self.store.get(order_id)

    async def update_order(self, order: OrderRecord) -> OrderRecord:
        self.store[order.order_id] = order
        return order


@dataclass(slots=True)
class InMemoryAccountsRepository(AccountsRepository):
    store: dict[str, AccountSnapshot]

    async def get_account(self, user_id: str) -> AccountSnapshot | None:
        return self.store.get(user_id)

    async def upsert_account(self, snapshot: AccountSnapshot) -> AccountSnapshot:
        self.store[snapshot.user_id] = snapshot
        return snapshot


@dataclass(slots=True)
class InMemoryPositionsRepository(PositionsRepository):
    store: dict[tuple[str, str], PositionRecord]

    async def get_position(self, user_id: str, instrument_id: str) -> PositionRecord | None:
        return self.store.get((user_id, instrument_id))

    async def upsert_position(self, position: PositionRecord) -> PositionRecord:
        self.store[(position.user_id, position.instrument_id)] = position
        return position


@dataclass(slots=True)
class InMemoryExecutionPublisher(ExecutionPublisher):
    published: list[ExecutionEvent]

    async def publish(self, event: ExecutionEvent) -> None:
        self.published.append(event)


class InMemoryTradingUnitOfWork(TradingUnitOfWork):
    def __init__(self) -> None:
        now = datetime.now(tz=timezone.utc)
        self.orders = InMemoryOrdersRepository(store={})
        self.accounts = InMemoryAccountsRepository(
            store={
                "user-123": AccountSnapshot(
                    user_id="user-123",
                    cash_balance=1_000_000.0,
                    base_currency="USD",
                    margin_allowed=True,
                    updated_at=now,
                )
            }
        )
        self.positions = InMemoryPositionsRepository(store={})
        self._committed = False

    async def __aenter__(self) -> "InMemoryTradingUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc:
            await self.rollback()
        else:
            await self.commit()

    async def commit(self) -> None:
        self._committed = True

    async def rollback(self) -> None:
        self._committed = False
