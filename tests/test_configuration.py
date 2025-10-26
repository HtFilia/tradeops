from datetime import timedelta

from market_data.configuration import (
    DealerQuoteSettings,
    InstrumentConfig,
    MarketDataConfig,
    OrderBookSettings,
    ScenarioSettings,
)
from market_data.generators.dealer_quotes import DealerQuoteGenerator
from market_data.generators.order_book import LadderOrderBookGenerator
from market_data.service import InstrumentFeed
from market_data.simulation.equity import GeometricBrownianMotionSimulator
from market_data.simulation.rates import MeanRevertingRateSimulator


def test_market_data_config_builds_equity_feed_with_order_book() -> None:
    config = MarketDataConfig(
        instruments=[
            InstrumentConfig(
                instrument_id="EQ-ALPHA",
                instrument_type="EQUITY",
                start_price=100.0,
                drift=0.01,
                volatility=0.2,
                step_seconds=1.0,
                tick_size=0.01,
                update_interval_ms=1000,
                seed=101,
                order_book=OrderBookSettings(
                    levels=3,
                    tick_size=0.01,
                    base_quantity=500.0,
                    quantity_decay=0.5,
                ),
            )
        ]
    )

    feeds = config.build_feeds()
    assert len(feeds) == 1
    feed = feeds[0]
    assert isinstance(feed, InstrumentFeed)
    assert isinstance(feed.simulator, GeometricBrownianMotionSimulator)
    assert feed.tick_size == 0.01
    assert feed.update_interval == timedelta(seconds=1)
    assert isinstance(feed.order_book_generator, LadderOrderBookGenerator)
    assert feed.dealer_quote_generator is None


def test_market_data_config_builds_rate_feed_with_dealer_quotes() -> None:
    config = MarketDataConfig(
        instruments=[
            InstrumentConfig(
                instrument_id="SWAP-5Y",
                instrument_type="RATE",
                start_price=0.015,
                mean_reversion=0.8,
                long_run_mean=0.017,
                volatility=0.001,
                step_seconds=1.0,
                tick_size=0.0001,
                update_interval_ms=1500,
                seed=202,
                dealer_quotes=DealerQuoteSettings(
                    dealers=["DEALER-A", "DEALER-B"],
                    base_spread=0.0004,
                    spread_volatility=0.0001,
                ),
            )
        ]
    )

    feed = config.build_feeds()[0]
    assert isinstance(feed.simulator, MeanRevertingRateSimulator)
    assert isinstance(feed.dealer_quote_generator, DealerQuoteGenerator)
    assert feed.order_book_generator is None
    assert feed.update_interval == timedelta(milliseconds=1500)


def test_market_data_config_supports_option_instrument() -> None:
    config = InstrumentConfig(
        instrument_id="OPT-AAPL-100C",
        instrument_type="OPTION",
        start_price=12.5,
        drift=0.0,
        volatility=0.3,
        step_seconds=1.0,
        tick_size=0.01,
        update_interval_ms=500,
        seed=77,
        underlier_instrument_id="EQ-AAPL",
    )

    feed = config.build_feed()
    assert isinstance(feed.simulator, GeometricBrownianMotionSimulator)
    assert feed.update_interval == timedelta(milliseconds=500)


def test_future_instrument_uses_equity_simulator_with_scenario() -> None:
    config = InstrumentConfig(
        instrument_id="FUT-ES",
        instrument_type="FUTURE",
        start_price=4300.0,
        drift=0.02,
        volatility=0.18,
        step_seconds=1.0,
        tick_size=0.25,
        update_interval_ms=100,
        scenario=ScenarioSettings(
            volatility_scale=1.5,
            drift_shift=-0.01,
            liquidity_regime="EXTREME",
        ),
    )

    feed = config.build_feed()
    assert feed.liquidity_regime == "EXTREME"
    assert feed.update_interval == timedelta(milliseconds=100)
    assert isinstance(feed.simulator, GeometricBrownianMotionSimulator)


def test_swap_instrument_applies_long_run_mean_shift_and_halt() -> None:
    config = InstrumentConfig(
        instrument_id="SWAP-10Y",
        instrument_type="SWAP",
        start_price=0.02,
        mean_reversion=1.0,
        long_run_mean=0.022,
        volatility=0.0012,
        step_seconds=1.0,
        tick_size=0.0001,
        update_interval_ms=500,
        scenario=ScenarioSettings(
            long_run_mean_shift=0.001,
            update_interval_ms_override=2000,
            halted=True,
        ),
    )

    feed = config.build_feed()
    assert feed.update_interval >= timedelta(days=1)
    assert isinstance(feed.simulator, MeanRevertingRateSimulator)
