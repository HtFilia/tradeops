from __future__ import annotations

import json

from redis.asyncio import Redis

from trading.domain.models import ExecutionEvent
from trading.ports.repositories import ExecutionPublisher


class RedisExecutionPublisher(ExecutionPublisher):
    def __init__(self, *, client: Redis, stream: str, maxlen: int | None = None) -> None:
        self._client = client
        self._stream = stream
        self._maxlen = maxlen

    async def publish(self, event: ExecutionEvent) -> None:
        payload = event.model_dump(mode="json")
        fields = {"payload": json.dumps(payload)}
        await self._client.xadd(self._stream, fields, maxlen=self._maxlen, approximate=True)
