from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from trading.domain.models import (
    DealerQuote,
    ExecutionEvent,
    LimitOrderRequest,
    ListedInstrumentBook,
    MarketOrderRequest,
    AccountSnapshot,
    OrderRecord,
    OrderStatus,
    OrderSide,
    OrderType,
    PositionRecord,
)


def test_limit_order_request_validates_positive_quantity() -> None:
    request = LimitOrderRequest(
        user_id="user-123",
        instrument_id="instr-abc",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=101.25,
        time_in_force="GTC",
    )
    assert request.order_type is OrderType.LIMIT


def test_limit_order_request_rejects_non_positive_quantity() -> None:
    with pytest.raises(ValidationError):
        LimitOrderRequest(
            user_id="user-123",
            instrument_id="instr-abc",
            side=OrderSide.SELL,
            quantity=0,
            limit_price=99.5,
            time_in_force="GTC",
        )


def test_market_order_request_derives_order_type() -> None:
    request = MarketOrderRequest(
        user_id="user-123",
        instrument_id="instr-abc",
        side=OrderSide.BUY,
        quantity=50,
    )
    assert request.order_type is OrderType.MARKET


def test_listed_instrument_book_requires_sorted_levels() -> None:
    book = ListedInstrumentBook(
        instrument_id="instr-abc",
        bids=[(100.5, 50), (100.0, 75)],
        asks=[(101.0, 40), (101.5, 80)],
        last_updated=datetime.now(tz=timezone.utc),
    )
    assert book.best_bid == (100.5, 50)
    assert book.best_ask == (101.0, 40)


def test_dealer_quote_requires_positive_spread() -> None:
    quote = DealerQuote(
        instrument_id="instr-otc",
        dealer_id="dealer-x",
        bid=99.5,
        ask=100.25,
        expires_at=datetime.now(tz=timezone.utc),
    )
    assert quote.mid_price == pytest.approx((99.5 + 100.25) / 2)


def test_execution_event_serialization_round_trip() -> None:
    event = ExecutionEvent(
        execution_id="fill-001",
        order_id="order-001",
        user_id="user-123",
        instrument_id="instr-abc",
        side=OrderSide.BUY,
        quantity=25,
        price=100.75,
        timestamp=datetime.now(tz=timezone.utc),
    )
    payload = event.model_dump()
    reconstructed = ExecutionEvent.model_validate(payload)
    assert reconstructed == event


def test_account_snapshot_requires_currency_code() -> None:
    snapshot = AccountSnapshot(
        user_id="user-123",
        cash_balance=1_000_000.0,
        base_currency="USD",
        margin_allowed=True,
        updated_at=datetime.now(tz=timezone.utc),
    )
    assert snapshot.cash_balance == 1_000_000.0


def test_position_record_normalizes_sign() -> None:
    position = PositionRecord(
        user_id="user-123",
        instrument_id="instr-abc",
        quantity=200,
        average_price=101.25,
        updated_at=datetime.now(tz=timezone.utc),
    )
    assert position.notional(105.0) == pytest.approx(21_000.0)


def test_order_record_computes_remaining_quantity() -> None:
    now = datetime.now(tz=timezone.utc)
    record = OrderRecord(
        order_id="order-001",
        user_id="user-123",
        instrument_id="instr-abc",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        filled_quantity=40,
        limit_price=100.5,
        status=OrderStatus.PARTIALLY_FILLED,
        time_in_force="GTC",
        created_at=now,
        updated_at=now,
    )
    assert record.remaining_quantity == 60


def test_order_record_rejects_overfill() -> None:
    now = datetime.now(tz=timezone.utc)
    with pytest.raises(ValidationError):
        OrderRecord(
            order_id="order-001",
            user_id="user-123",
            instrument_id="instr-abc",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            filled_quantity=120,
            limit_price=100.5,
            status=OrderStatus.FILLED,
            time_in_force="GTC",
            created_at=now,
            updated_at=now,
        )
