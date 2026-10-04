"""Capabilities of the shipped synthetic demo, not inferred from tick availability."""
from pydantic import BaseModel


class InstrumentCapability(BaseModel):
    instrument_id: str
    display_name: str
    tradable: bool
    quote_unit: str
    order_types: list[str]
    reason: str | None = None


DEMO_INSTRUMENTS = [
    InstrumentCapability(instrument_id="EQ-ACME", display_name="Synthetic equity", tradable=True,
                         quote_unit="currency_units", order_types=["MARKET", "LIMIT"]),
    InstrumentCapability(instrument_id="BOND-5Y", display_name="Synthetic 5-year rate", tradable=False,
                         quote_unit="annual_decimal_rate", order_types=[],
                         reason="Quote-only rate feed; bond execution is not implemented."),
    InstrumentCapability(instrument_id="FUT-ES", display_name="Synthetic index-future quote", tradable=False,
                         quote_unit="index_points", order_types=[],
                         reason="Quote-only feed; futures execution and margin are not implemented."),
]


def quote_only(instrument_id: str) -> bool:
    return any(row.instrument_id == instrument_id and not row.tradable for row in DEMO_INSTRUMENTS)
