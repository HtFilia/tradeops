from __future__ import annotations

from abc import ABC, abstractmethod
import random


class RandomProcessSimulator(ABC):
    """Common functionality for seeded stochastic simulators."""

    def __init__(self, instrument_id: str, seed: int | None = None) -> None:
        self.instrument_id = instrument_id
        self._seed = seed
        self._rng = random.Random(seed)
        self._initialize_state()

    @abstractmethod
    def _initialize_state(self) -> None:
        """Reset internal state to initial conditions."""

    def reset(self) -> None:
        """Reset the simulator to its initial seeded state."""
        self._rng = random.Random(self._seed)
        self._initialize_state()
