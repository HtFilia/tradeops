from datetime import datetime, timezone

from market_data.generators.order_book import LadderOrderBookGenerator, OrderBookDepthConfig


def test_ladder_order_book_generator_produces_sorted_levels() -> None:
    generator = LadderOrderBookGenerator(
        instrument_id="EQ-BOOK",
        config=OrderBookDepthConfig(
            levels=3,
            tick_size=0.01,
            base_quantity=500.0,
            quantity_decay=0.6,
        ),
        seed=42,
    )

    timestamp = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    snapshot = generator.build(mid_price=100.0, timestamp=timestamp)

    assert snapshot.instrument_id == "EQ-BOOK"
    assert snapshot.timestamp == timestamp

    bids = snapshot.bids
    asks = snapshot.asks

    assert len(bids) == len(asks) == 3
    assert bids[0].price < 100.0 < asks[0].price

    # Prices should step away from mid according to tick size.
    expected_bid_prices = [99.99, 99.98, 99.97]
    expected_ask_prices = [100.01, 100.02, 100.03]
    assert [round(level.price, 2) for level in bids] == expected_bid_prices
    assert [round(level.price, 2) for level in asks] == expected_ask_prices

    # Quantities should decay geometrically.
    expected_quantities = [500.0, 300.0, 180.0]
    assert [round(level.quantity, 1) for level in bids] == expected_quantities
    assert [round(level.quantity, 1) for level in asks] == expected_quantities


def test_ladder_order_book_generator_with_noise_preserves_spread() -> None:
    generator = LadderOrderBookGenerator(
        instrument_id="EQ-NOISE",
        config=OrderBookDepthConfig(
            levels=2,
            tick_size=0.05,
            base_quantity=100.0,
            quantity_decay=0.5,
            price_noise=0.2,
        ),
        seed=7,
    )

    snapshot = generator.build(mid_price=50.0, timestamp=datetime.now(tz=timezone.utc))

    assert snapshot.bids[0].price < snapshot.asks[0].price
    assert all(b.price < a.price for b, a in zip(snapshot.bids, snapshot.asks))
