from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import random
from typing import Iterable, List, Optional

from market_data.models import DealerQuoteEvent


@dataclass(frozen=True)
class DealerQuoteConfig:
    base_spread: float
    spread_volatility: float = 0.0
    min_spread: float = 1e-5

    def __post_init__(self) -> None:
        if self.base_spread <= 0:
            raise ValueError("base_spread must be positive")
        if self.spread_volatility < 0:
            raise ValueError("spread_volatility must be non-negative")
        if self.min_spread <= 0:
            raise ValueError("min_spread must be positive")


class DealerQuoteGenerator:
    """Generate dealer-specific OTC quotes with deterministic optional randomness."""

    def __init__(
        self,
        instrument_id: str,
        dealers: Iterable[str],
        base_spread: float,
        spread_volatility: float = 0.0,
        min_spread: float = 1e-5,
        seed: Optional[int] = None,
    ) -> None:
        dealer_list = list(dealers)
        if not dealer_list:
            raise ValueError("dealers must contain at least one dealer id")

        self._instrument_id = instrument_id
        self._dealers = dealer_list
        self._config = DealerQuoteConfig(
            base_spread=base_spread,
            spread_volatility=spread_volatility,
            min_spread=min_spread,
        )
        self._rng = random.Random(seed)

    def generate(self, mid_rate: float, timestamp: datetime) -> List[DealerQuoteEvent]:
        if mid_rate <= 0:
            raise ValueError("mid_rate must be positive")

        quotes: List[DealerQuoteEvent] = []

        for dealer_id in self._dealers:
            spread = self._config.base_spread
            if self._config.spread_volatility > 0:
                spread += self._rng.normalvariate(0.0, self._config.spread_volatility)
            spread = max(spread, self._config.min_spread)

            half_spread = spread / 2.0
            bid = mid_rate - half_spread
            ask = mid_rate + half_spread

            quotes.append(
                DealerQuoteEvent(
                    instrument_id=self._instrument_id,
                    dealer_id=dealer_id,
                    timestamp=timestamp,
                    bid=round(bid, 6),
                    ask=round(ask, 6),
                )
            )

        return quotes
