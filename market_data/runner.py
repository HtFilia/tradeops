from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from market_data.service import MarketDataService

SleepCallable = Callable[[float], Awaitable[None]]


class MarketDataRunner:
    """Simple event loop driver for the market data service."""

    def __init__(
        self,
        service: MarketDataService,
        interval_seconds: float = 0.1,
        sleeper: SleepCallable | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")

        self._service = service
        self._interval = interval_seconds
        self._sleep: SleepCallable = sleeper if sleeper is not None else asyncio.sleep

    async def run(self, iterations: int | None = None) -> None:
        """Pump the service either forever or for a bounded number of iterations."""
        count = 0
        while iterations is None or count < iterations:
            await self._service.pump_once()
            count += 1
            await self._sleep(self._interval)


async def run_forever(service: MarketDataService, interval_seconds: float = 0.1) -> None:
    """Helper to continuously run the market data service at the given cadence."""
    runner = MarketDataRunner(service=service, interval_seconds=interval_seconds)
    await runner.run()
