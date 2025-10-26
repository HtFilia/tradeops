from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Iterable

from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field, ValidationError

try:
    from pydantic import ValidationInfo, field_validator, model_validator

    PYDANTIC_V2 = True
except ImportError:  # pragma: no cover - exercised when running under pydantic v1
    ValidationInfo = Any  # type: ignore
    field_validator = None  # type: ignore
    model_validator = None  # type: ignore
    PYDANTIC_V2 = False

from pydantic import root_validator, validator  # available for v1 compatibility


class EventModel(PydanticBaseModel):
    """Compatibility wrapper exposing Pydantic v2 style helpers."""

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if PYDANTIC_V2:
            return super().model_dump(*args, **kwargs)  # type: ignore[attr-defined]
        return super().dict(*args, **kwargs)

    def model_dump_json(self, *args: Any, **kwargs: Any) -> str:
        json_kwargs = {
            key: kwargs.pop(key)
            for key in ("indent", "separators", "sort_keys", "ensure_ascii")
            if key in kwargs
        }
        data = self.model_dump(*args, **kwargs)
        normalized = _normalize_json_ready(data)
        return json.dumps(normalized, **json_kwargs)


def _normalize_json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_json_ready(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value.endswith("Z") and value.count("T") == 1:
        return value[:-1] + "+00:00"
    return value


class TickEvent(EventModel):
    instrument_id: str
    timestamp: datetime
    bid: float
    ask: float
    mid: float
    liquidity_regime: str
    metadata: dict[str, Any] | None = None

    if PYDANTIC_V2:

        @model_validator(mode="after")
        def validate_prices(self) -> "TickEvent":
            if self.bid > self.mid or self.mid > self.ask:
                raise ValueError("Bid-mid-ask relationship must satisfy bid <= mid <= ask")
            return self

    else:

        @root_validator(skip_on_failure=True)
        def validate_prices(cls, values: dict[str, Any]) -> dict[str, Any]:
            bid = values.get("bid")
            mid = values.get("mid")
            ask = values.get("ask")
            if None not in (bid, mid, ask) and not (bid <= mid <= ask):
                raise ValueError("Bid-mid-ask relationship must satisfy bid <= mid <= ask")
            return values


class OrderBookLevel(EventModel):
    price: float = Field(..., alias="price")
    quantity: float = Field(..., gt=0, alias="quantity")


def _is_descending(levels: Iterable[OrderBookLevel]) -> bool:
    prices = [level.price for level in levels]
    return all(prices[i] >= prices[i + 1] for i in range(len(prices) - 1))


def _is_ascending(levels: Iterable[OrderBookLevel]) -> bool:
    prices = [level.price for level in levels]
    return all(prices[i] <= prices[i + 1] for i in range(len(prices) - 1))


class OrderBookSnapshot(EventModel):
    instrument_id: str
    timestamp: datetime
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]

    if PYDANTIC_V2:

        @model_validator(mode="after")
        def validate_depth(self) -> "OrderBookSnapshot":
            if self.bids and not _is_descending(self.bids):
                raise ValueError("Bid levels must be sorted descending by price")
            if self.asks and not _is_ascending(self.asks):
                raise ValueError("Ask levels must be sorted ascending by price")
            if self.bids and self.asks and self.bids[0].price >= self.asks[0].price:
                raise ValueError("Best bid must be strictly below best ask")
            return self

    else:

        @root_validator(skip_on_failure=True)
        def validate_depth(cls, values: dict[str, Any]) -> dict[str, Any]:
            bids: list[OrderBookLevel] = values.get("bids", [])
            asks: list[OrderBookLevel] = values.get("asks", [])

            if bids and not _is_descending(bids):
                raise ValueError("Bid levels must be sorted descending by price")
            if asks and not _is_ascending(asks):
                raise ValueError("Ask levels must be sorted ascending by price")
            if bids and asks and bids[0].price >= asks[0].price:
                raise ValueError("Best bid must be strictly below best ask")
            return values


class DealerQuoteEvent(EventModel):
    instrument_id: str
    dealer_id: str
    timestamp: datetime
    bid: float
    ask: float
    metadata: dict[str, Any] | None = None

    if PYDANTIC_V2:

        @field_validator("ask")
        def validate_spread(cls, ask: float, info: ValidationInfo) -> float:
            bid = info.data.get("bid") if info is not None else None
            if bid is not None and ask <= bid:
                raise ValueError("Dealer ask must be strictly greater than bid")
            return ask

    else:

        @validator("ask")
        def validate_spread(cls, ask: float, values: dict[str, Any]) -> float:
            bid = values.get("bid")
            if bid is not None and ask is not None and ask <= bid:
                raise ValueError("Dealer ask must be strictly greater than bid")
            return ask


__all__ = [
    "DealerQuoteEvent",
    "OrderBookLevel",
    "OrderBookSnapshot",
    "TickEvent",
    "ValidationError",
]
