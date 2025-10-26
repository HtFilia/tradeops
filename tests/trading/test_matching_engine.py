from datetime import datetime, timezone

from trading.domain.matching import MatchingEngine
from trading.domain.models import LimitOrderRequest, ListedInstrumentBook, OrderSide


def build_book() -> ListedInstrumentBook:
    return ListedInstrumentBook(
        instrument_id="instr-abc",
        bids=[(99.5, 100), (99.0, 200)],
        asks=[(100.5, 150), (101.0, 100)],
        last_updated=datetime.now(tz=timezone.utc),
    )


def test_limit_buy_order_matches_against_order_book() -> None:
    order = LimitOrderRequest(
        user_id="user-123",
        instrument_id="instr-abc",
        side=OrderSide.BUY,
        quantity=180,
        limit_price=101.0,
        time_in_force="GTC",
    )
    engine = MatchingEngine()
    fills, residual = engine.match(order, build_book())
    assert residual == 0
    assert len(fills) == 2
    assert fills[0].price == 100.5 and fills[0].quantity == 150
    assert fills[1].price == 101.0 and fills[1].quantity == 30


def test_limit_sell_order_partial_fill() -> None:
    order = LimitOrderRequest(
        user_id="user-123",
        instrument_id="instr-abc",
        side=OrderSide.SELL,
        quantity=350,
        limit_price=99.0,
        time_in_force="GTC",
    )
    engine = MatchingEngine()
    fills, residual = engine.match(order, build_book())
    assert residual == 50
    assert fills[0].price == 99.5
    assert fills[0].quantity == 100
    assert fills[1].price == 99.0
    assert fills[1].quantity == 200
