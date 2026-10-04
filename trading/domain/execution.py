from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from trading.domain.exceptions import (
    InsufficientBalanceError,
    InsufficientPositionError,
)
from trading.domain.matching import MatchingEngine, Fill
from trading.domain.models import (
    AccountSnapshot,
    BaseOrderRequest,
    ListedInstrumentBook,
    OrderSide,
    OrderStatus,
    PositionRecord,
)


@dataclass(frozen=True)
class ExecutionPlan:
    fills: list[Fill]
    residual: int
    account: AccountSnapshot
    position: PositionRecord | None
    consideration: float
    status: OrderStatus


def prepare_execution(
    order: BaseOrderRequest,
    book: ListedInstrumentBook,
    account: AccountSnapshot,
    position: PositionRecord | None,
    now: datetime,
    engine: MatchingEngine,
) -> ExecutionPlan:
    if order.side is OrderSide.SELL:
        _validate_sell_quantity(order, position)
    fills, residual = engine.match(order, book)
    quantity = sum(f.quantity for f in fills)
    consideration = sum(f.price * f.quantity for f in fills)
    if order.side is OrderSide.BUY:
        _validate_balance(account, consideration)
    updated_account = _apply_cash_mutation(
        account=account,
        order_side=order.side,
        total_consideration=consideration,
        timestamp=now,
    )
    updated_position = (
        _apply_position_mutation(
            order_request=order,
            existing_position=position,
            filled_quantity=quantity,
            total_consideration=consideration,
            timestamp=now,
        )
        if quantity
        else position
    )
    return ExecutionPlan(
        fills,
        residual,
        updated_account,
        updated_position,
        consideration,
        _derive_status(quantity, residual),
    )


def _validate_balance(account: AccountSnapshot, required_cash: float) -> None:
    if required_cash > account.cash_balance + 1e-9:
        raise InsufficientBalanceError("insufficient cash to execute order")


def _validate_sell_quantity(
    order_request: BaseOrderRequest,
    position: PositionRecord | None,
) -> None:
    position_qty = position.quantity if position else 0
    if position_qty < order_request.quantity:
        raise InsufficientPositionError("order quantity exceeds available position")


def _apply_cash_mutation(
    *,
    account: AccountSnapshot,
    order_side: OrderSide,
    total_consideration: float,
    timestamp: datetime,
) -> AccountSnapshot:
    if total_consideration == 0:
        return account.model_copy(update={"updated_at": timestamp})
    delta = -total_consideration if order_side is OrderSide.BUY else total_consideration
    return account.model_copy(
        update={
            "cash_balance": account.cash_balance + delta,
            "updated_at": timestamp,
        }
    )


def _apply_position_mutation(
    *,
    order_request: BaseOrderRequest,
    existing_position: PositionRecord | None,
    filled_quantity: int,
    total_consideration: float,
    timestamp: datetime,
) -> PositionRecord:
    if order_request.side is OrderSide.BUY:
        prior_qty = existing_position.quantity if existing_position else 0
        prior_cost = (
            (existing_position.average_price * prior_qty) if existing_position else 0.0
        )
        new_qty = prior_qty + filled_quantity
        new_avg_price = (prior_cost + total_consideration) / max(new_qty, 1)
    else:
        if existing_position is None:
            raise InsufficientPositionError("no position to sell")
        prior_qty = existing_position.quantity
        if filled_quantity > prior_qty:
            raise InsufficientPositionError("execution exceeds owned quantity")
        new_qty = prior_qty - filled_quantity
        new_avg_price = (
            existing_position.average_price
            if new_qty > 0
            else existing_position.average_price
        )

    return PositionRecord(
        user_id=order_request.user_id,
        instrument_id=order_request.instrument_id,
        quantity=new_qty,
        average_price=new_avg_price,
        updated_at=timestamp,
    )


def _derive_status(filled_quantity: int, residual: int) -> OrderStatus:
    if filled_quantity == 0:
        return OrderStatus.NEW
    if residual == 0:
        return OrderStatus.FILLED
    return OrderStatus.PARTIALLY_FILLED
