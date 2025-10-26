from datetime import date

from market_data.metadata import future_contract_metadata_factory, swap_curve_metadata_factory


def test_swap_curve_metadata_factory_generates_curve_buckets() -> None:
    factory = swap_curve_metadata_factory(
        tenor="10Y",
        curve_points={"1Y": 0.018, "5Y": 0.021, "10Y": 0.024},
        dv01_per_million=780.5,
    )

    metadata = factory(0.0235)

    assert metadata["instrument_type"] == "SWAP"
    assert metadata["tenor"] == "10Y"
    assert metadata["curve"]["10Y"] == 0.024
    assert metadata["dv01_per_million"] == 780.5
    assert metadata["mark"] == 0.0235


def test_future_contract_metadata_factory_includes_expiry_and_tick_value() -> None:
    factory = future_contract_metadata_factory(
        symbol="ESM4",
        contract_month="2024-06",
        expiry=date(2024, 6, 21),
        tick_value=12.5,
        multiplier=50,
    )

    metadata = factory(4350.25)

    assert metadata["instrument_type"] == "FUTURE"
    assert metadata["symbol"] == "ESM4"
    assert metadata["expiry"] == "2024-06-21"
    assert metadata["tick_value"] == 12.5
    assert metadata["notional"] == 4350.25 * 50
