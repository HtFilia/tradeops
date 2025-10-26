import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from market_data.models import DealerQuoteEvent, OrderBookSnapshot, TickEvent


def test_tick_event_contract_serializes_expected_fields() -> None:
    event = TickEvent(
        instrument_id="EQ-ABC",
        timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        bid=99.95,
        ask=100.05,
        mid=100.0,
        liquidity_regime="HIGH",
        metadata={"spread_bps": 10},
    )

    payload = json.loads(event.model_dump_json())
    assert payload == {
        "instrument_id": "EQ-ABC",
        "timestamp": "2024-01-01T12:00:00+00:00",
        "bid": 99.95,
        "ask": 100.05,
        "mid": 100.0,
        "liquidity_regime": "HIGH",
        "metadata": {"spread_bps": 10},
    }


def test_order_book_snapshot_requires_sorted_levels() -> None:
    snapshot = OrderBookSnapshot(
        instrument_id="EQ-ABC",
        timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        bids=[
            {"price": 99.9, "quantity": 500},
            {"price": 99.8, "quantity": 300},
        ],
        asks=[
            {"price": 100.1, "quantity": 400},
            {"price": 100.2, "quantity": 600},
        ],
    )

    payload = json.loads(snapshot.model_dump_json())
    assert payload["bids"][0]["price"] >= payload["bids"][1]["price"]
    assert payload["asks"][0]["price"] <= payload["asks"][1]["price"]


def test_order_book_snapshot_rejects_unordered_depth() -> None:
    with pytest.raises(ValidationError):
        OrderBookSnapshot(
            instrument_id="EQ-ABC",
            timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            bids=[
                {"price": 99.8, "quantity": 300},
                {"price": 99.9, "quantity": 500},
            ],
            asks=[
                {"price": 100.2, "quantity": 600},
                {"price": 100.1, "quantity": 400},
            ],
        )


def test_dealer_quote_event_validates_positive_spread() -> None:
    quote = DealerQuoteEvent(
        instrument_id="SWAP-5Y",
        dealer_id="DEALER-A",
        timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        bid=0.0125,
        ask=0.013,
        metadata={"tenor": "5Y"},
    )

    assert quote.ask > quote.bid

    with pytest.raises(ValidationError):
        DealerQuoteEvent(
            instrument_id="SWAP-5Y",
            dealer_id="DEALER-A",
            timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            bid=0.013,
            ask=0.0125,
        )
