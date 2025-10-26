from __future__ import annotations

import math

from .base import RandomProcessSimulator


class GeometricBrownianMotionSimulator(RandomProcessSimulator):
    """Seeded geometric Brownian motion price path simulator."""

    def __init__(
        self,
        instrument_id: str,
        start_price: float,
        drift: float,
        volatility: float,
        step_seconds: float,
        seed: int | None = None,
    ) -> None:
        if start_price <= 0:
            raise ValueError("start_price must be positive")
        if volatility < 0:
            raise ValueError("volatility must be non-negative")
        if step_seconds <= 0:
            raise ValueError("step_seconds must be positive")

        self._start_price = start_price
        self._price = start_price
        self._drift = drift
        self._volatility = volatility
        self._step_seconds = step_seconds

        super().__init__(instrument_id=instrument_id, seed=seed)

    def _initialize_state(self) -> None:
        self._price = self._start_price

    def _step(self) -> float:
        shock = self._rng.normalvariate(0.0, 1.0)
        drift_term = (self._drift - 0.5 * self._volatility**2) * self._step_seconds
        diffusion_term = self._volatility * math.sqrt(self._step_seconds) * shock
        self._price *= math.exp(drift_term + diffusion_term)
        return self._price

    def next_price(self) -> float:
        """Advance the process by one time step and return the new price."""
        return self._step()

    def next_value(self) -> float:
        """Alias used by generic service interfaces."""
        return self.next_price()
