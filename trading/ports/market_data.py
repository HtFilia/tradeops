from __future__ import annotations

from typing import Protocol, runtime_checkable

from trading.domain.models import ListedInstrumentBook


@runtime_checkable
class MarketDataGateway(Protocol):
    async def get_order_book(self, instrument_id: str) -> ListedInstrumentBook:
        ...
