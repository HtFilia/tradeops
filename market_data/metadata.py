from __future__ import annotations

from datetime import date
from typing import Callable, Mapping

MetadataFactory = Callable[[float], dict[str, object]]


def swap_curve_metadata_factory(
    tenor: str,
    curve_points: Mapping[str, float],
    dv01_per_million: float,
) -> MetadataFactory:
    """Return a metadata factory capturing swap curve context."""

    def factory(mark: float) -> dict[str, object]:
        return {
            "instrument_type": "SWAP",
            "tenor": tenor,
            "curve": dict(curve_points),
            "dv01_per_million": dv01_per_million,
            "mark": mark,
        }

    return factory


def future_contract_metadata_factory(
    symbol: str,
    contract_month: str,
    expiry: date,
    tick_value: float,
    multiplier: float,
) -> MetadataFactory:
    """Return metadata factory for listed futures contracts."""

    def factory(mark: float) -> dict[str, object]:
        return {
            "instrument_type": "FUTURE",
            "symbol": symbol,
            "contract_month": contract_month,
            "expiry": expiry.isoformat(),
            "tick_value": tick_value,
            "multiplier": multiplier,
            "notional": mark * multiplier,
        }

    return factory


__all__ = [
    "future_contract_metadata_factory",
    "swap_curve_metadata_factory",
]
