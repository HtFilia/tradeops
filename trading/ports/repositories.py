from __future__ import annotations

from typing import Protocol, runtime_checkable

from trading.domain.models import AccountSnapshot, ExecutionEvent, OrderRecord, PositionRecord


@runtime_checkable
class OrdersRepository(Protocol):
    async def create_order(self, order: OrderRecord) -> OrderRecord:
        ...

    async def get_order(self, order_id: str) -> OrderRecord | None:
        ...

    async def update_order(self, order: OrderRecord) -> OrderRecord:
        ...


@runtime_checkable
class AccountsRepository(Protocol):
    async def get_account(self, user_id: str) -> AccountSnapshot | None:
        ...

    async def upsert_account(self, snapshot: AccountSnapshot) -> AccountSnapshot:
        ...


@runtime_checkable
class PositionsRepository(Protocol):
    async def get_position(self, user_id: str, instrument_id: str) -> PositionRecord | None:
        ...

    async def upsert_position(self, position: PositionRecord) -> PositionRecord:
        ...


@runtime_checkable
class ExecutionPublisher(Protocol):
    async def publish(self, event: ExecutionEvent) -> None:
        ...


@runtime_checkable
class TradingUnitOfWork(Protocol):
    orders: OrdersRepository
    accounts: AccountsRepository
    positions: PositionsRepository

    async def __aenter__(self) -> "TradingUnitOfWork":
        ...

    async def __aexit__(self, exc_type, exc, tb) -> None:
        ...

    async def commit(self) -> None:
        ...

    async def rollback(self) -> None:
        ...
