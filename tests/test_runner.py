import asyncio

from market_data.runner import MarketDataRunner


class RecordingService:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def pump_once(self) -> None:
        self.calls.append(asyncio.get_event_loop().time())


class RecordingSleeper:
    def __init__(self) -> None:
        self.intervals: list[float] = []

    async def __call__(self, interval: float) -> None:
        self.intervals.append(interval)


def test_runner_invokes_service_and_sleep() -> None:
    service = RecordingService()
    sleeper = RecordingSleeper()
    runner = MarketDataRunner(service=service, interval_seconds=0.2, sleeper=sleeper)

    asyncio.run(runner.run(iterations=3))

    assert len(service.calls) == 3
    assert sleeper.intervals == [0.2, 0.2, 0.2]
