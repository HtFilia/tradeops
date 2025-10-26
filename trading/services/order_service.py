from __future__ import annotations

from datetime import datetime
from typing import Callable

from trading.domain.exceptions import (
    InsufficientBalanceError,
    InsufficientPositionError,
    OrderValidationError,
)
from trading.domain.matching import MatchingEngine
from trading.domain.models import (
    AccountSnapshot,
    BaseOrderRequest,
    ExecutionEvent,
    ListedInstrumentBook,
    OrderRecord,
    OrderSide,
    OrderStatus,
    PositionRecord,
)
from trading.ports.repositories import ExecutionPublisher, TradingUnitOfWork
from common.logging import get_logger

logger = get_logger("trading.order_service")


class OrderService:
    def __init__(
        self,
        *,
        uow_factory: Callable[[], TradingUnitOfWork],
        matching_engine: MatchingEngine,
        execution_publisher: ExecutionPublisher,
        id_generator: Callable[[], str],
        clock: Callable[[], datetime],
    ) -> None:
        self._uow_factory = uow_factory
        self._matching_engine = matching_engine
        self._execution_publisher = execution_publisher
        self._id_generator = id_generator
        self._clock = clock

    async def submit(
        self,
        order_request: BaseOrderRequest,
        book: ListedInstrumentBook,
    ) -> OrderRecord:
        order_id = self._id_generator()
        now = self._clock()
        async with self._uow_factory() as uow:
            logger.info(
                "Submitting order",
                extra={
                    "event": "trading.order.submit",
                    "context": {
                        "order_id": order_id,
                        "user_id": order_request.user_id,
                        "instrument_id": order_request.instrument_id,
                        "side": order_request.side.value,
                        "order_type": order_request.order_type.value,
                        "quantity": order_request.quantity,
                    },
                },
            )
            account = await uow.accounts.get_account(order_request.user_id)
            if account is None:
                raise OrderValidationError("account not found for user")

            existing_position = await uow.positions.get_position(
                order_request.user_id,
                order_request.instrument_id,
            )

            if order_request.side is OrderSide.SELL:
                self._validate_sell_quantity(order_request, existing_position)

            fills, residual = self._matching_engine.match(order_request, book)
            filled_quantity = sum(fill.quantity for fill in fills)
            total_consideration = sum(fill.price * fill.quantity for fill in fills)

            if order_request.side is OrderSide.BUY:
                self._validate_balance(account, total_consideration)

            updated_account = self._apply_cash_mutation(
                account=account,
                order_side=order_request.side,
                total_consideration=total_consideration,
                timestamp=now,
            )

            if filled_quantity > 0:
                updated_position = self._apply_position_mutation(
                    order_request=order_request,
                    existing_position=existing_position,
                    filled_quantity=filled_quantity,
                    total_consideration=total_consideration,
                    timestamp=now,
                )
                await uow.positions.upsert_position(updated_position)

            await uow.accounts.upsert_account(updated_account)

            average_price = (
                total_consideration / filled_quantity if filled_quantity > 0 else None
            )
            status = self._derive_status(filled_quantity, residual)
            order_record = OrderRecord(
                order_id=order_id,
                user_id=order_request.user_id,
                instrument_id=order_request.instrument_id,
                side=order_request.side,
                order_type=order_request.order_type,
                quantity=order_request.quantity,
                filled_quantity=filled_quantity,
                limit_price=getattr(order_request, "limit_price", None),
                average_price=average_price,
                status=status,
                time_in_force=getattr(order_request, "time_in_force", "GTC"),
                created_at=now,
                updated_at=now,
            )
            await uow.orders.create_order(order_record)

            if filled_quantity > 0:
                execution_event = ExecutionEvent(
                    execution_id=f"{order_id}-exec",
                    order_id=order_id,
                    user_id=order_request.user_id,
                    instrument_id=order_request.instrument_id,
                    side=order_request.side,
                    quantity=filled_quantity,
                    price=average_price or 0.0,
                    timestamp=now,
                )
                await self._execution_publisher.publish(execution_event)
                logger.info(
                    "Order filled",
                    extra={
                        "event": "trading.order.filled",
                        "context": {
                            "order_id": order_id,
                            "filled_quantity": filled_quantity,
                            "average_price": average_price,
                            "status": status.value,
                        },
                    },
                )
            else:
                logger.info(
                    "Order accepted with no fills",
                    extra={
                        "event": "trading.order.accepted",
                        "context": {
                            "order_id": order_id,
                            "status": status.value,
                        },
                    },
                )

            return order_record

    def _validate_balance(self, account: AccountSnapshot, required_cash: float) -> None:
        if required_cash > account.cash_balance + 1e-9:
            raise InsufficientBalanceError("insufficient cash to execute order")

    def _validate_sell_quantity(
        self,
        order_request: BaseOrderRequest,
        position: PositionRecord | None,
    ) -> None:
        position_qty = position.quantity if position else 0
        if position_qty < order_request.quantity:
            raise InsufficientPositionError("order quantity exceeds available position")

    def _apply_cash_mutation(
        self,
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
        self,
        *,
        order_request: BaseOrderRequest,
        existing_position: PositionRecord | None,
        filled_quantity: int,
        total_consideration: float,
        timestamp: datetime,
    ) -> PositionRecord:
        if order_request.side is OrderSide.BUY:
            prior_qty = existing_position.quantity if existing_position else 0
            prior_cost = (existing_position.average_price * prior_qty) if existing_position else 0.0
            new_qty = prior_qty + filled_quantity
            new_avg_price = (prior_cost + total_consideration) / max(new_qty, 1)
        else:
            if existing_position is None:
                raise InsufficientPositionError("no position to sell")
            prior_qty = existing_position.quantity
            if filled_quantity > prior_qty:
                raise InsufficientPositionError("execution exceeds owned quantity")
            new_qty = prior_qty - filled_quantity
            new_avg_price = existing_position.average_price if new_qty > 0 else existing_position.average_price

        return PositionRecord(
            user_id=order_request.user_id,
            instrument_id=order_request.instrument_id,
            quantity=new_qty,
            average_price=new_avg_price,
            updated_at=timestamp,
        )

    @staticmethod
    def _derive_status(filled_quantity: int, residual: int) -> OrderStatus:
        if filled_quantity == 0:
            return OrderStatus.NEW
        if residual == 0:
            return OrderStatus.FILLED
        return OrderStatus.PARTIALLY_FILLED
