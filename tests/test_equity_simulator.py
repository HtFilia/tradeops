import math
import random

import pytest

from market_data.simulation.equity import GeometricBrownianMotionSimulator


def gbm_expected_path(
    start_price: float,
    drift: float,
    volatility: float,
    step_seconds: float,
    seed: int,
    steps: int,
) -> list[float]:
    """Helper to compute the deterministic reference path for assertions."""
    rng = random.Random(seed)
    price = start_price
    path = []
    drift_term = (drift - 0.5 * volatility**2) * step_seconds
    diffusion_scale = volatility * math.sqrt(step_seconds)

    for _ in range(steps):
        shock = rng.normalvariate(0.0, 1.0)
        price *= math.exp(drift_term + diffusion_scale * shock)
        path.append(round(price, 6))
    return path


@pytest.mark.parametrize(
    "drift,volatility,step_seconds",
    [
        (0.01, 0.2, 1.0),
        (0.0, 0.05, 0.5),
    ],
)
def test_equity_simulator_produces_deterministic_gbm_path(
    drift: float, volatility: float, step_seconds: float
) -> None:
    simulator = GeometricBrownianMotionSimulator(
        instrument_id="EQ-TEST",
        start_price=100.0,
        drift=drift,
        volatility=volatility,
        step_seconds=step_seconds,
        seed=1234,
    )

    observed = [round(simulator.next_price(), 6) for _ in range(5)]
    expected = gbm_expected_path(
        start_price=100.0,
        drift=drift,
        volatility=volatility,
        step_seconds=step_seconds,
        seed=1234,
        steps=5,
    )

    assert observed == expected, "GBM simulator deviated from seeded expectation"
