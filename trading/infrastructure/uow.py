from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import asyncpg

from trading.domain.models import AccountSnapshot, OrderRecord, OrderSide, OrderStatus, OrderType, PositionRecord
from trading.ports.repositories import AccountsRepository, OrdersRepository, PositionsRepository, TradingUnitOfWork


def _serialize_order(order: OrderRecord) -> dict[str, Any]:
    return {
        "order_id": order.order_id,
        "user_id": order.user_id,
        "instrument_id": order.instrument_id,
        "side": order.side.value,
        "order_type": order.order_type.value,
        "quantity": order.quantity,
        "filled_quantity": order.filled_quantity,
        "limit_price": order.limit_price,
        "average_price": order.average_price,
        "status": order.status.value,
        "time_in_force": order.time_in_force,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }


def _deserialize_order(record: asyncpg.Record) -> OrderRecord:
    return OrderRecord(
        order_id=record["order_id"],
        user_id=record["user_id"],
        instrument_id=record["instrument_id"],
        side=OrderSide(record["side"]),
        order_type=OrderType(record["order_type"]),
        quantity=record["quantity"],
        filled_quantity=record["filled_quantity"],
        limit_price=record["limit_price"],
        average_price=record["average_price"],
        status=OrderStatus(record["status"]),
        time_in_force=record["time_in_force"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


def _deserialize_account(record: asyncpg.Record) -> AccountSnapshot:
    return AccountSnapshot(
        user_id=str(record["user_id"]),
        cash_balance=record["cash_balance"],
        base_currency=record["base_currency"],
        margin_allowed=record["margin_allowed"],
        updated_at=record["updated_at"],
    )


def _deserialize_position(record: asyncpg.Record) -> PositionRecord:
    return PositionRecord(
        user_id=str(record["user_id"]),
        instrument_id=record["instrument_id"],
        quantity=record["quantity"],
        average_price=record["average_price"],
        updated_at=record["updated_at"],
    )


@dataclass(slots=True)
class AsyncpgOrdersRepository(OrdersRepository):
    connection: asyncpg.Connection

    async def create_order(self, order: OrderRecord) -> OrderRecord:
        payload = _serialize_order(order)
        await self.connection.execute(
            """
            INSERT INTO orders (
                order_id,
                user_id,
                instrument_id,
                side,
                order_type,
                quantity,
                filled_quantity,
                limit_price,
                average_price,
                status,
                time_in_force,
                created_at,
                updated_at
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13
            )
            ON CONFLICT (order_id) DO UPDATE SET
                filled_quantity = EXCLUDED.filled_quantity,
                average_price = EXCLUDED.average_price,
                status = EXCLUDED.status,
                updated_at = EXCLUDED.updated_at
            """,
            payload["order_id"],
            payload["user_id"],
            payload["instrument_id"],
            payload["side"],
            payload["order_type"],
            payload["quantity"],
            payload["filled_quantity"],
            payload["limit_price"],
            payload["average_price"],
            payload["status"],
            payload["time_in_force"],
            payload["created_at"],
            payload["updated_at"],
        )
        return order

    async def get_order(self, order_id: str) -> OrderRecord | None:
        record = await self.connection.fetchrow("SELECT * FROM orders WHERE order_id = $1", order_id)
        if record is None:
            return None
        return _deserialize_order(record)

    async def update_order(self, order: OrderRecord) -> OrderRecord:
        payload = _serialize_order(order)
        await self.connection.execute(
            """
            UPDATE orders SET
                filled_quantity = $2,
                average_price = $3,
                status = $4,
                updated_at = $5
            WHERE order_id = $1
            """,
            payload["order_id"],
            payload["filled_quantity"],
            payload["average_price"],
            payload["status"],
            payload["updated_at"],
        )
        return order


@dataclass(slots=True)
class AsyncpgAccountsRepository(AccountsRepository):
    connection: asyncpg.Connection

    async def get_account(self, user_id: str) -> AccountSnapshot | None:
        record = await self.connection.fetchrow("SELECT * FROM accounts WHERE user_id = $1", user_id)
        if record is None:
            return None
        return _deserialize_account(record)

    async def upsert_account(self, snapshot: AccountSnapshot) -> AccountSnapshot:
        await self.connection.execute(
            """
            INSERT INTO accounts (user_id, cash_balance, base_currency, margin_allowed, updated_at)
            VALUES ($1,$2,$3,$4,$5)
            ON CONFLICT (user_id) DO UPDATE SET
                cash_balance = EXCLUDED.cash_balance,
                margin_allowed = EXCLUDED.margin_allowed,
                updated_at = EXCLUDED.updated_at
            """,
            snapshot.user_id,
            snapshot.cash_balance,
            snapshot.base_currency,
            snapshot.margin_allowed,
            snapshot.updated_at,
        )
        return snapshot


@dataclass(slots=True)
class AsyncpgPositionsRepository(PositionsRepository):
    connection: asyncpg.Connection

    async def get_position(self, user_id: str, instrument_id: str) -> PositionRecord | None:
        record = await self.connection.fetchrow(
            "SELECT * FROM positions WHERE user_id = $1 AND instrument_id = $2",
            user_id,
            instrument_id,
        )
        if record is None:
            return None
        return _deserialize_position(record)

    async def upsert_position(self, position: PositionRecord) -> PositionRecord:
        await self.connection.execute(
            """
            INSERT INTO positions (user_id, instrument_id, quantity, average_price, updated_at)
            VALUES ($1,$2,$3,$4,$5)
            ON CONFLICT (user_id, instrument_id) DO UPDATE SET
                quantity = EXCLUDED.quantity,
                average_price = EXCLUDED.average_price,
                updated_at = EXCLUDED.updated_at
            """,
            position.user_id,
            position.instrument_id,
            position.quantity,
            position.average_price,
            position.updated_at,
        )
        return position


class AsyncpgTradingUnitOfWork(TradingUnitOfWork):
    def __init__(self, *, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._connection: asyncpg.Connection | None = None
        self._transaction: asyncpg.Transaction | None = None
        self.orders: OrdersRepository
        self.accounts: AccountsRepository
        self.positions: PositionsRepository

    async def __aenter__(self) -> "AsyncpgTradingUnitOfWork":
        self._connection = await self._pool.acquire()
        self._transaction = self._connection.transaction()
        await self._transaction.start()
        self.orders = AsyncpgOrdersRepository(self._connection)
        self.accounts = AsyncpgAccountsRepository(self._connection)
        self.positions = AsyncpgPositionsRepository(self._connection)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._transaction is None or self._connection is None:
            return
        try:
            if exc:
                await self._transaction.rollback()
            else:
                await self._transaction.commit()
        finally:
            await self._pool.release(self._connection)
            self._transaction = None
            self._connection = None

    async def commit(self) -> None:
        if self._transaction is None:
            raise RuntimeError("transaction not started")
        await self._transaction.commit()
        self._transaction = self._connection.transaction()
        await self._transaction.start()

    async def rollback(self) -> None:
        if self._transaction is None:
            return
        await self._transaction.rollback()
        self._transaction = self._connection.transaction()
        await self._transaction.start()
