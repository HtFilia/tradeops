from __future__ import annotations

from datetime import datetime
from typing import Callable

from trading.domain.exceptions import (
    OrderValidationError,
)
from trading.domain.execution import prepare_execution
from trading.domain.matching import MatchingEngine
from trading.domain.models import (
    BaseOrderRequest,
    ExecutionEvent,
    ListedInstrumentBook,
    OrderRecord,
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

            plan = prepare_execution(
                order_request,
                book,
                account,
                existing_position,
                now,
                self._matching_engine,
            )
            filled_quantity = sum(fill.quantity for fill in plan.fills)
            if filled_quantity and plan.position is not None:
                await uow.positions.upsert_position(plan.position)
            await uow.accounts.upsert_account(plan.account)
            average_price = (
                plan.consideration / filled_quantity if filled_quantity else None
            )
            status = plan.status
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
