from __future__ import annotations

import math

from .base import RandomProcessSimulator


class MeanRevertingRateSimulator(RandomProcessSimulator):
    """Ornstein-Uhlenbeck process for short-rate / DV01 style simulations."""

    def __init__(
        self,
        instrument_id: str,
        start_rate: float,
        mean_reversion: float,
        long_run_mean: float,
        volatility: float,
        step_seconds: float,
        seed: int | None = None,
    ) -> None:
        if step_seconds <= 0:
            raise ValueError("step_seconds must be positive")
        if volatility < 0:
            raise ValueError("volatility must be non-negative")
        if mean_reversion < 0:
            raise ValueError("mean_reversion must be non-negative")

        self._start_rate = start_rate
        self._rate = start_rate
        self._mean_reversion = mean_reversion
        self._long_run_mean = long_run_mean
        self._volatility = volatility
        self._step_seconds = step_seconds

        super().__init__(instrument_id=instrument_id, seed=seed)

    def _initialize_state(self) -> None:
        self._rate = self._start_rate

    def _step(self) -> float:
        shock = self._rng.normalvariate(0.0, 1.0)
        dt = self._step_seconds
        drift_component = self._mean_reversion * (self._long_run_mean - self._rate) * dt
        diffusion_component = self._volatility * math.sqrt(dt) * shock
        self._rate += drift_component + diffusion_component
        return self._rate

    def next_rate(self) -> float:
        """Advance the process by one time step and return the updated rate."""
        return self._step()

    def next_value(self) -> float:
        """Alias used by generic service interfaces."""
        return self.next_rate()
