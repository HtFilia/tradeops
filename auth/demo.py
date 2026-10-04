"""Guest creation uses the existing PostgreSQL users and Redis cookie sessions."""

import asyncio
import secrets
from dataclasses import replace
from auth.security import Argon2PasswordHasher
from datetime import timedelta
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Request, Response
from auth.app import _set_session_cookie
from auth.configuration import AuthConfig
from auth.models import SessionResponse
from auth.session import RedisSessionStore, SessionToken
from common.demo_limits import (
    DEMO_TTL_MINUTES,
    DEMO_MAX_GUESTS,
    require_same_origin,
    throttle,
)
from auth.storage import SupportsAcquire
from redis.asyncio import Redis


def demo_router(
    pool: SupportsAcquire, redis: Redis, config: AuthConfig, origins: list[str]
) -> APIRouter:
    router = APIRouter(prefix="/auth/demo", tags=["isolated demo"])
    guest_config = replace(config, session_ttl_minutes=DEMO_TTL_MINUTES)
    sessions = RedisSessionStore(redis, timedelta(minutes=DEMO_TTL_MINUTES))

    @router.post("/start", response_model=SessionResponse)
    async def start(request: Request, response: Response) -> SessionResponse:
        require_same_origin(request, origins)
        token = request.cookies.get(config.session_cookie_name)
        previous = await sessions.get(SessionToken(token)) if token else None
        if previous:
            async with pool.acquire() as conn:
                guest = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM demo_guests WHERE user_id=$1 AND expires_at>NOW())",
                    previous.user_id,
                )
            if guest:
                return SessionResponse(
                    user_id=previous.user_id,
                    expires_at=previous.expires_at,
                    principal_kind="guest",
                )
        await throttle(redis, request, "start", 5)
        owner, generation = uuid4(), uuid4()
        password_hash = await asyncio.to_thread(
            Argon2PasswordHasher().hash, secrets.token_urlsafe(32)
        )
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(731205)")
            active = await conn.fetchval(
                "SELECT COUNT(*) FROM demo_guests WHERE expires_at>NOW()"
            )
            if active >= DEMO_MAX_GUESTS:
                raise HTTPException(503, "Demo capacity reached. Try again later.")
            await conn.execute(
                "INSERT INTO users(id,email,password_hash,principal_kind) VALUES($1,$2,$3,'guest')",
                owner,
                f"{owner}@demo.invalid",
                password_hash,
            )
            await conn.execute(
                "INSERT INTO accounts(user_id,cash_balance,base_currency) VALUES($1,10000,'USD')",
                owner,
            )
            await conn.execute(
                "INSERT INTO demo_guests(user_id,expires_at) VALUES($1,NOW()+$2::interval)",
                owner,
                timedelta(minutes=DEMO_TTL_MINUTES),
            )
            await conn.execute(
                "INSERT INTO demo_cases(user_id,generation,case_id) VALUES($1,$2,'full')",
                owner,
                generation,
            )
        session = await sessions.issue(str(owner), principal_kind="guest")
        _set_session_cookie(response, session.token, session.expires_at, guest_config)
        return SessionResponse(
            user_id=session.user_id,
            expires_at=session.expires_at,
            principal_kind="guest",
        )

    return router
