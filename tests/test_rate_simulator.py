import math
import random

import pytest

from market_data.simulation.rates import MeanRevertingRateSimulator


def ornstein_uhlenbeck_reference_path(
    start_rate: float,
    mean_reversion: float,
    long_run_mean: float,
    volatility: float,
    step_seconds: float,
    seed: int,
    steps: int,
) -> list[float]:
    """Generate the reference path for an Ornstein-Uhlenbeck rate process."""
    rng = random.Random(seed)
    rate = start_rate
    path: list[float] = []
    dt = step_seconds
    diffusion_scale = volatility * math.sqrt(dt)

    for _ in range(steps):
        shock = rng.normalvariate(0.0, 1.0)
        rate += mean_reversion * (long_run_mean - rate) * dt + diffusion_scale * shock
        path.append(round(rate, 6))
    return path


@pytest.mark.parametrize(
    "mean_reversion,long_run_mean,volatility",
    [
        (0.5, 0.01, 0.002),
        (1.2, 0.015, 0.0015),
    ],
)
def test_rate_simulator_matches_seeded_ornstein_uhlenbeck_path(
    mean_reversion: float, long_run_mean: float, volatility: float
) -> None:
    simulator = MeanRevertingRateSimulator(
        instrument_id="RATE-TEST",
        start_rate=0.0125,
        mean_reversion=mean_reversion,
        long_run_mean=long_run_mean,
        volatility=volatility,
        step_seconds=1.0,
        seed=2024,
    )

    observed = [round(simulator.next_rate(), 6) for _ in range(6)]
    expected = ornstein_uhlenbeck_reference_path(
        start_rate=0.0125,
        mean_reversion=mean_reversion,
        long_run_mean=long_run_mean,
        volatility=volatility,
        step_seconds=1.0,
        seed=2024,
        steps=6,
    )

    assert observed == expected, "Rate simulator produced non-deterministic results"
