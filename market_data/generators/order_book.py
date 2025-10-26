from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import random
from typing import Optional

from market_data.models import OrderBookLevel, OrderBookSnapshot


@dataclass(frozen=True)
class OrderBookDepthConfig:
    levels: int
    tick_size: float
    base_quantity: float
    quantity_decay: float = 0.7
    price_noise: float = 0.0

    def __post_init__(self) -> None:
        if self.levels <= 0:
            raise ValueError("levels must be positive")
        if self.tick_size <= 0:
            raise ValueError("tick_size must be positive")
        if self.base_quantity <= 0:
            raise ValueError("base_quantity must be positive")
        if not 0 < self.quantity_decay <= 1:
            raise ValueError("quantity_decay must lie in (0, 1]")
        if self.price_noise < 0:
            raise ValueError("price_noise must be non-negative")


class LadderOrderBookGenerator:
    """Generate deterministic ladder-style order books with optional noise."""

    def __init__(
        self,
        instrument_id: str,
        config: OrderBookDepthConfig,
        seed: Optional[int] = None,
    ) -> None:
        self._instrument_id = instrument_id
        self._config = config
        self._rng = random.Random(seed)

    def build(self, mid_price: float, timestamp: datetime) -> OrderBookSnapshot:
        if mid_price <= 0:
            raise ValueError("mid_price must be positive")

        bids: list[OrderBookLevel] = []
        asks: list[OrderBookLevel] = []

        for level in range(self._config.levels):
            price_offset = self._config.tick_size * (level + 1)
            noise = self._rng.normalvariate(0.0, self._config.price_noise) if self._config.price_noise else 0.0

            bid_price = mid_price - price_offset - noise
            ask_price = mid_price + price_offset + noise

            quantity = self._config.base_quantity * (self._config.quantity_decay ** level)

            bids.append(OrderBookLevel(price=round(bid_price, 6), quantity=round(quantity, 6)))
            asks.append(OrderBookLevel(price=round(ask_price, 6), quantity=round(quantity, 6)))

        return OrderBookSnapshot(
            instrument_id=self._instrument_id,
            timestamp=timestamp,
            bids=bids,
            asks=asks,
        )
