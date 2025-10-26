from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Iterable, List, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


class BaseOrderRequest(BaseModel):
    user_id: str
    instrument_id: str
    side: OrderSide
    quantity: int
    order_type: OrderType

    model_config = ConfigDict(frozen=True)

    @field_validator("quantity")
    @classmethod
    def _validate_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be positive")
        return value


class LimitOrderRequest(BaseOrderRequest):
    limit_price: float
    time_in_force: str = Field(default="GTC")
    order_type: OrderType = Field(default=OrderType.LIMIT, frozen=True)

    @field_validator("limit_price")
    @classmethod
    def _validate_limit_price(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("limit_price must be positive")
        return value


class MarketOrderRequest(BaseOrderRequest):
    order_type: OrderType = Field(default=OrderType.MARKET, frozen=True)


class ListedInstrumentBook(BaseModel):
    instrument_id: str
    bids: List[Tuple[float, int]]
    asks: List[Tuple[float, int]]
    last_updated: datetime

    model_config = ConfigDict(frozen=True)

    @field_validator("bids")
    @classmethod
    def _validate_bids(cls, value: Sequence[Tuple[float, int]]) -> List[Tuple[float, int]]:
        cls._validate_depth(value, descending=True)
        return list(value)

    @field_validator("asks")
    @classmethod
    def _validate_asks(cls, value: Sequence[Tuple[float, int]]) -> List[Tuple[float, int]]:
        cls._validate_depth(value, descending=False)
        return list(value)

    @staticmethod
    def _validate_depth(levels: Sequence[Tuple[float, int]], *, descending: bool) -> None:
        prices: Iterable[float] = (price for price, _ in levels)
        quantities: Iterable[int] = (qty for _, qty in levels)
        previous: float | None = None
        for price in prices:
            if price <= 0:
                raise ValueError("price levels must be positive")
            if previous is not None:
                if descending and price > previous:
                    raise ValueError("bid levels must be sorted in descending price order")
                if not descending and price < previous:
                    raise ValueError("ask levels must be sorted in ascending price order")
            previous = price
        for qty in quantities:
            if qty <= 0:
                raise ValueError("quantities must be positive")

    @computed_field(return_type=Tuple[float, int] | None)
    def best_bid(self) -> Tuple[float, int] | None:
        return self.bids[0] if self.bids else None

    @computed_field(return_type=Tuple[float, int] | None)
    def best_ask(self) -> Tuple[float, int] | None:
        return self.asks[0] if self.asks else None


class DealerQuote(BaseModel):
    instrument_id: str
    dealer_id: str
    bid: float
    ask: float
    expires_at: datetime

    model_config = ConfigDict(frozen=True)

    @field_validator("bid", "ask")
    @classmethod
    def _validate_price(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("quote prices must be positive")
        return value

    @field_validator("ask")
    @classmethod
    def _validate_bid_ask_relation(cls, ask: float, info) -> float:
        bid = info.data.get("bid")
        if bid is not None and ask <= bid:
            raise ValueError("ask price must be greater than bid price")
        return ask

    @computed_field(return_type=float)
    def mid_price(self) -> float:
        return (self.bid + self.ask) / 2.0


class ExecutionEvent(BaseModel):
    execution_id: str
    order_id: str
    user_id: str
    instrument_id: str
    side: OrderSide
    quantity: int
    price: float
    timestamp: datetime

    model_config = ConfigDict(frozen=True)


class OrderRecord(BaseModel):
    order_id: str
    user_id: str
    instrument_id: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    filled_quantity: int
    limit_price: float | None
    average_price: float | None = None
    status: OrderStatus
    time_in_force: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(frozen=True)

    @field_validator("quantity")
    @classmethod
    def _validate_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be positive")
        return value

    @field_validator("filled_quantity")
    @classmethod
    def _validate_filled_quantity(cls, value: int, info) -> int:
        if value < 0:
            raise ValueError("filled_quantity must be non-negative")
        quantity = info.data.get("quantity")
        if quantity is not None and value > quantity:
            raise ValueError("filled_quantity cannot exceed total quantity")
        return value

    @field_validator("average_price")
    @classmethod
    def _validate_average_price(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("average_price must be positive when provided")
        return value

    @computed_field(return_type=int)
    def remaining_quantity(self) -> int:
        return self.quantity - self.filled_quantity


class AccountSnapshot(BaseModel):
    user_id: str
    cash_balance: float
    base_currency: str
    margin_allowed: bool
    updated_at: datetime

    model_config = ConfigDict(frozen=True)

    @field_validator("base_currency")
    @classmethod
    def _validate_currency(cls, value: str) -> str:
        if len(value) != 3 or not value.isalpha():
            raise ValueError("base_currency must be a 3-letter ISO code")
        return value.upper()


class PositionRecord(BaseModel):
    user_id: str
    instrument_id: str
    quantity: int
    average_price: float
    updated_at: datetime

    model_config = ConfigDict(frozen=True)

    @field_validator("average_price")
    @classmethod
    def _validate_average_price(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("average_price must be positive")
        return value

    def notional(self, current_price: float) -> float:
        return current_price * float(self.quantity)
