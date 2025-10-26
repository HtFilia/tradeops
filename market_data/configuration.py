from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Iterable, Literal, Mapping, Sequence

from market_data.generators.dealer_quotes import DealerQuoteGenerator
from market_data.generators.order_book import LadderOrderBookGenerator, OrderBookDepthConfig
from market_data.service import DealerQuoteSource, InstrumentFeed, OrderBookGenerator
from market_data.simulation.equity import GeometricBrownianMotionSimulator
from market_data.simulation.rates import MeanRevertingRateSimulator
from market_data.metadata import future_contract_metadata_factory, swap_curve_metadata_factory


MetadataFactory = Callable[[float], dict[str, float]]


@dataclass
class OrderBookSettings:
    levels: int
    tick_size: float
    base_quantity: float
    quantity_decay: float = 0.7
    price_noise: float = 0.0

    def to_generator(self, instrument_id: str, seed: int | None) -> OrderBookGenerator:
        config = OrderBookDepthConfig(
            levels=self.levels,
            tick_size=self.tick_size,
            base_quantity=self.base_quantity,
            quantity_decay=self.quantity_decay,
            price_noise=self.price_noise,
        )
        return LadderOrderBookGenerator(
            instrument_id=instrument_id,
            config=config,
            seed=seed,
        )


@dataclass
class DealerQuoteSettings:
    dealers: Sequence[str]
    base_spread: float
    spread_volatility: float = 0.0
    min_spread: float = 1e-5

    def to_generator(self, instrument_id: str, seed: int | None) -> DealerQuoteSource:
        return DealerQuoteGenerator(
            instrument_id=instrument_id,
            dealers=self.dealers,
            base_spread=self.base_spread,
            spread_volatility=self.spread_volatility,
            min_spread=self.min_spread,
            seed=seed,
        )


InstrumentType = Literal["EQUITY", "RATE", "OPTION", "FUTURE", "SWAP"]


@dataclass
class ScenarioSettings:
    volatility_scale: float | None = None
    drift_shift: float | None = None
    long_run_mean_shift: float | None = None
    liquidity_regime: str | None = None
    update_interval_ms_override: int | None = None
    halted: bool = False


@dataclass
class InstrumentConfig:
    instrument_id: str
    instrument_type: InstrumentType
    start_price: float
    tick_size: float
    step_seconds: float
    update_interval_ms: int
    liquidity_regime: str = "MEDIUM"
    seed: int | None = None
    drift: float | None = None
    volatility: float | None = None
    mean_reversion: float | None = None
    long_run_mean: float | None = None
    underlier_instrument_id: str | None = None
    tenor: str | None = None
    contract_month: str | None = None
    curve_points: Mapping[str, float] | None = None
    dv01_per_million: float | None = None
    tick_value: float | None = None
    multiplier: float | None = None
    order_book: OrderBookSettings | None = None
    dealer_quotes: DealerQuoteSettings | None = None
    metadata_factory: MetadataFactory | None = None
    scenario: ScenarioSettings | None = None
    scenario_name: str | None = None

    def build_feed(self) -> InstrumentFeed:
        scenario = self.scenario or (
            PRESET_SCENARIOS[self.scenario_name] if self.scenario_name else ScenarioSettings()
        )
        generator = self._build_simulator(scenario)
        metadata_factory = self._choose_metadata_factory()
        order_book_generator = (
            self.order_book.to_generator(self.instrument_id, self.seed) if self.order_book else None
        )
        dealer_quote_generator = (
            self.dealer_quotes.to_generator(self.instrument_id, self.seed) if self.dealer_quotes else None
        )

        liquidity_regime = scenario.liquidity_regime or self.liquidity_regime
        update_interval_ms = scenario.update_interval_ms_override or self.update_interval_ms
        if scenario.halted:
            update_interval_ms = max(update_interval_ms, 86_400_000)  # effectively halt

        return InstrumentFeed(
            instrument_id=self.instrument_id,
            simulator=generator,
            tick_size=self.tick_size,
            liquidity_regime=liquidity_regime,
            update_interval=timedelta(milliseconds=update_interval_ms),
            metadata_factory=metadata_factory,
            order_book_generator=order_book_generator,
            dealer_quote_generator=dealer_quote_generator,
        )

    def _choose_metadata_factory(self) -> MetadataFactory | None:
        if self.metadata_factory is not None:
            return self.metadata_factory

        if self.instrument_type in ("SWAP", "RATE") and self.tenor and self.curve_points and self.dv01_per_million is not None:
            return swap_curve_metadata_factory(
                tenor=self.tenor,
                curve_points=self.curve_points,
                dv01_per_million=self.dv01_per_million,
            )

        if self.instrument_type in ("FUTURE", "OPTION") and self.contract_month and self.tick_value and self.multiplier:
            symbol = self.instrument_id
            return future_contract_metadata_factory(
                symbol=symbol,
                contract_month=self.contract_month,
                expiry=_contract_month_to_date(self.contract_month),
                tick_value=self.tick_value,
                multiplier=self.multiplier,
            )

        return None

    def _build_simulator(self, scenario: ScenarioSettings):
        if self.instrument_type in ("EQUITY", "OPTION", "FUTURE"):
            if self.drift is None or self.volatility is None:
                raise ValueError(f"{self.instrument_type} instruments require drift and volatility")
            drift = self.drift + (scenario.drift_shift or 0.0)
            volatility = self.volatility * (scenario.volatility_scale or 1.0)
            return GeometricBrownianMotionSimulator(
                instrument_id=self.instrument_id,
                start_price=self.start_price,
                drift=drift,
                volatility=volatility,
                step_seconds=self.step_seconds,
                seed=self.seed,
            )

        if self.instrument_type in ("RATE", "SWAP"):
            if self.mean_reversion is None or self.long_run_mean is None or self.volatility is None:
                raise ValueError(f"{self.instrument_type} instruments require mean_reversion, long_run_mean, and volatility")
            long_run_mean = self.long_run_mean + (scenario.long_run_mean_shift or 0.0)
            volatility = self.volatility * (scenario.volatility_scale or 1.0)
            return MeanRevertingRateSimulator(
                instrument_id=self.instrument_id,
                start_rate=self.start_price,
                mean_reversion=self.mean_reversion,
                long_run_mean=long_run_mean,
                volatility=volatility,
                step_seconds=self.step_seconds,
                seed=self.seed,
            )

        raise ValueError(f"Unsupported instrument_type '{self.instrument_type}'")


@dataclass
class MarketDataConfig:
    instruments: Iterable[InstrumentConfig] = field(default_factory=list)

    def build_feeds(self) -> list[InstrumentFeed]:
        return [instrument.build_feed() for instrument in self.instruments]


PRESET_SCENARIOS: dict[str, ScenarioSettings] = {
    "volatile": ScenarioSettings(volatility_scale=1.5, liquidity_regime="LOW", update_interval_ms_override=1500),
    "halted": ScenarioSettings(halted=True, update_interval_ms_override=86_400_000),
    "rally": ScenarioSettings(drift_shift=0.01, liquidity_regime="HIGH"),
}


def _contract_month_to_date(contract_month: str) -> date:
    year, month = contract_month.split("-")
    return date(int(year), int(month), 1)
