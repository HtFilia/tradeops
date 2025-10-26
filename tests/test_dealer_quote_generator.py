from datetime import datetime, timezone

from market_data.generators.dealer_quotes import DealerQuoteGenerator


def test_dealer_quote_generator_emits_quotes_with_positive_spread() -> None:
    generator = DealerQuoteGenerator(
        instrument_id="SWAP-5Y",
        dealers=["DEALER-A", "DEALER-B"],
        base_spread=0.0005,
        spread_volatility=0.0002,
        seed=99,
    )

    timestamp = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    quotes = generator.generate(mid_rate=0.015, timestamp=timestamp)

    assert len(quotes) == 2
    for quote in quotes:
        assert quote.instrument_id == "SWAP-5Y"
        assert quote.timestamp == timestamp
        assert quote.ask > quote.bid
        assert 0.014 < quote.bid < 0.016
        assert 0.015 < quote.ask < 0.017
