"""Versioned immutable snapshot cases; no shared market liquidity consumption."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from trading.domain.models import (
    ListedInstrumentBook,
    MarketOrderRequest,
    LimitOrderRequest,
    BaseOrderRequest,
)

CaseId = Literal["full", "partial", "limit", "rejection"]
FIXTURE_VERSION = "equity-snapshots-v1"
FIXTURE_TIME = datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc)


@dataclass(frozen=True)
class DemoCase:
    name: str
    description: str
    book: ListedInstrumentBook
    action: dict[str, object]


def _book(shallow: bool = False) -> ListedInstrumentBook:
    return ListedInstrumentBook(
        instrument_id="EQ-ACME",
        bids=[(99.9, 3), (99.8, 4)],
        asks=[(100.0, 2), (100.2, 1)] if shallow else [(100.0, 3), (100.1, 4)],
        last_updated=FIXTURE_TIME,
    )


CASES: dict[str, DemoCase] = {
    "full": DemoCase(
        "Full fill",
        "Five shares sweep two price levels.",
        _book(),
        {"side": "BUY", "quantity": 5, "order_type": "MARKET"},
    ),
    "partial": DemoCase(
        "Shallow book",
        "Only three shares are available; two remain unfilled, final.",
        _book(True),
        {"side": "BUY", "quantity": 5, "order_type": "MARKET"},
    ),
    "limit": DemoCase(
        "Non-crossing limit",
        "A 99.90 buy limit cannot reach the 100.00 ask.",
        _book(),
        {"side": "BUY", "quantity": 5, "order_type": "LIMIT", "limit_price": 99.9},
    ),
    "rejection": DemoCase(
        "Position rejection",
        "Selling without holdings is rejected before matching.",
        _book(),
        {"side": "SELL", "quantity": 1, "order_type": "MARKET"},
    ),
}


class DemoResetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    generation: UUID
    case_id: CaseId


class DemoOrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    generation: UUID
    snapshot_id: str = Field(min_length=1, max_length=128)
    idempotency_key: UUID
    instrument_id: Literal["EQ-ACME"] = "EQ-ACME"
    side: Literal["BUY", "SELL"]
    quantity: int = Field(gt=0, le=10000, strict=True)
    order_type: Literal["MARKET", "LIMIT"]
    limit_price: float | None = Field(default=None, gt=0, le=1000000)

    @model_validator(mode="after")
    def validate_limit(self) -> "DemoOrderInput":
        if (self.order_type == "LIMIT") != (self.limit_price is not None):
            raise ValueError("A limit price is required only for LIMIT orders")
        return self

    def to_domain_request(self, owner: str) -> BaseOrderRequest:
        fields = dict(
            user_id=owner,
            instrument_id=self.instrument_id,
            side=self.side,
            quantity=self.quantity,
        )
        return (
            LimitOrderRequest(**fields, limit_price=self.limit_price)
            if self.order_type == "LIMIT"
            else MarketOrderRequest(**fields)
        )
