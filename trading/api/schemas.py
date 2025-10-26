from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trading.domain.models import (
    LimitOrderRequest,
    MarketOrderRequest,
    OrderRecord,
    OrderSide,
    OrderStatus,
    OrderType,
)


class OrderCreateRequest(BaseModel):
    user_id: str
    instrument_id: str
    side: OrderSide
    quantity: int = Field(gt=0)
    order_type: OrderType
    limit_price: float | None = Field(default=None, gt=0)
    time_in_force: str | None = None

    model_config = ConfigDict(use_enum_values=False)

    @model_validator(mode="after")
    def _validate_limit_price(self) -> "OrderCreateRequest":
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit_price required for limit orders")
        return self

    def to_domain_request(self) -> LimitOrderRequest | MarketOrderRequest:
        if self.order_type is OrderType.MARKET:
            return MarketOrderRequest(
                user_id=self.user_id,
                instrument_id=self.instrument_id,
                side=self.side,
                quantity=self.quantity,
            )
        return LimitOrderRequest(
            user_id=self.user_id,
            instrument_id=self.instrument_id,
            side=self.side,
            quantity=self.quantity,
            limit_price=float(self.limit_price),
            time_in_force=self.time_in_force or "GTC",
        )


class OrderResponse(BaseModel):
    order_id: str
    instrument_id: str
    side: OrderSide
    quantity: int
    filled_quantity: int
    status: OrderStatus
    average_price: float | None

    model_config = ConfigDict(use_enum_values=False)

    @classmethod
    def from_domain(cls, order: OrderRecord) -> "OrderResponse":
        return cls(
            order_id=order.order_id,
            instrument_id=order.instrument_id,
            side=order.side,
            quantity=order.quantity,
            filled_quantity=order.filled_quantity,
            status=order.status,
            average_price=order.average_price,
        )
