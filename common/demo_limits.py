"""Configured resource bounds, not measured capacity claims."""

import os
from hashlib import sha256
from fastapi import HTTPException, Request
from redis.asyncio import Redis


def bounded_setting(name: str, default: int, maximum: int) -> int:
    value = int(os.getenv(name, str(default)))
    if not 1 <= value <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


DEMO_TTL_MINUTES = bounded_setting("DEMO_TTL_MINUTES", 120, 1440)
DEMO_MAX_GUESTS = bounded_setting("DEMO_MAX_GUESTS", 200, 10000)
DEMO_MAX_SUBMISSIONS = bounded_setting("DEMO_MAX_SUBMISSIONS", 100, 1000)
DEMO_MAX_RESETS = bounded_setting("DEMO_MAX_RESETS", 20, 100)


def require_same_origin(request: Request, origins: list[str]) -> None:
    origin = request.headers.get("origin")
    own = str(request.base_url).rstrip("/")
    if (origin and origin != own and origin not in origins) or request.headers.get(
        "sec-fetch-site"
    ) == "cross-site":
        raise HTTPException(403, "Cross-origin demo mutation is forbidden")
    if request.headers.get("content-type", "").split(";")[0] != "application/json":
        raise HTTPException(415, "Demo mutations require application/json")


async def throttle(redis: Redis, request: Request, action: str, maximum: int) -> None:
    # Use the server-resolved peer, never an arbitrary browser-supplied owner/IP.
    peer = request.client.host if request.client else "unknown"
    digest = sha256(peer.encode()).hexdigest()[:24]
    key = f"demo_rate:{action}:{digest}"
    count = await redis.eval(
        "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],60) end; return n",
        1,
        key,
    )
    if count > maximum:
        raise HTTPException(
            429,
            "Too many demo starts/resets. Try again in one minute.",
            headers={"Retry-After": "60"},
        )
