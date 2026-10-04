"""Default live feeds use seconds internally and explicit annual GBM inputs."""

import math
import random

import pytest

from market_data.app import DEFAULT_INSTRUMENTS


@pytest.mark.parametrize("instrument_id,annual_drift,annual_vol", [
    ("EQ-ACME", 0.05, 0.2), ("FUT-ES", 0.01, 0.18),
])
def test_default_gbm_matches_annual_closed_form_after_four_hours(
    instrument_id: str, annual_drift: float, annual_vol: float
) -> None:
    config = next(item for item in DEFAULT_INSTRUMENTS if item.instrument_id == instrument_id)
    seconds_per_year = 365 * 24 * 60 * 60
    dt = config.update_interval_ms / 1000
    assert config.step_seconds == dt
    steps = int(4 * 60 * 60 / dt)
    rng = random.Random(config.seed)
    shocks = math.fsum(rng.normalvariate(0, 1) for _ in range(steps))
    years = steps * dt / seconds_per_year
    expected = config.start_price * math.exp(
        (annual_drift - 0.5 * annual_vol**2) * years
        + annual_vol * math.sqrt(dt / seconds_per_year) * shocks
    )
    simulator = config.build_feed().simulator
    for _ in range(steps):
        actual = simulator.next_value()
    # Independent terminal log-price formula versus iterative multiplication.
    assert actual == pytest.approx(expected, rel=1e-11)
