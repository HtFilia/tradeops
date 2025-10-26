from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


async def retry_async(
    func: Callable[..., Awaitable[T]],
    *args,
    attempts: int = 3,
    base_delay: float = 0.05,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    **kwargs,
) -> T:
    if attempts <= 0:
        raise ValueError("attempts must be positive")

    sleeper = sleep or asyncio.sleep
    last_error: BaseException | None = None

    for attempt in range(1, attempts + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover - exercised in tests
            last_error = exc
            if attempt == attempts:
                raise
            await sleeper(base_delay * attempt)

    assert last_error is not None
    raise last_error


__all__ = ["retry_async"]
