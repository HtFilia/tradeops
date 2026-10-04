"""Opt-in real PostgreSQL + Redis tests. Never point these at a deployed database."""

import asyncio
import os
from uuid import uuid4
import asyncpg
import httpx
import pytest
import pytest_asyncio
from redis.asyncio import Redis
from auth.server import create_default_app as auth_app
from common.schema import prepare_schema
from trading.app import create_default_app as trading_app
from trading.config import TradingSettings
from trading.infrastructure.uow import AsyncpgOrdersRepository

DSN = os.getenv("DEMO_TEST_POSTGRES_DSN")
REDIS = os.getenv("DEMO_TEST_REDIS_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not DSN or not REDIS, reason="isolated real demo test services not configured"
    ),
]


@pytest_asyncio.fixture
async def stack(monkeypatch):
    assert DSN.endswith("/demo_test"), "Only a dedicated demo_test database is allowed"
    assert ":18579/" in REDIS, "Only the documented isolated test Redis port is allowed"
    pool = await asyncpg.create_pool(DSN)
    await prepare_schema(pool, "public")
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE users CASCADE")
    redis = Redis.from_url(REDIS)
    await redis.flushdb()
    monkeypatch.setenv("AUTH_POSTGRES_DSN", DSN)
    monkeypatch.setenv("AUTH_REDIS_URL", REDIS)
    monkeypatch.setenv("AUTH_SECURE_COOKIES", "false")
    a = auth_app()
    t = trading_app(TradingSettings(postgres_dsn=DSN, redis_url=REDIS))
    async with a.router.lifespan_context(a), t.router.lifespan_context(t):
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=a), base_url="http://demo.local"
            ) as auth,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=t, raise_app_exceptions=False),
                base_url="http://demo.local",
            ) as trade,
        ):
            yield auth, trade, pool, redis
    await pool.close()
    await redis.aclose()


async def start(auth, trade):
    response = await auth.post("/auth/demo/start", json={})
    assert response.status_code == 200, response.text
    assert (
        "HttpOnly" in response.headers["set-cookie"]
        and "SameSite=lax" in response.headers["set-cookie"]
    )
    trade.cookies.update(auth.cookies)
    return response.json()


async def order(trade, **overrides):
    account = (await trade.get("/demo/account")).json()
    book = (await trade.get("/demo/book")).json()
    return dict(
        generation=account["generation"],
        snapshot_id=book["snapshot_id"],
        idempotency_key=str(uuid4()),
        side="BUY",
        quantity=5,
        order_type="MARKET",
        **overrides,
    )


@pytest.mark.asyncio
async def test_full_receipt_reconciles_and_survives_retry_and_refresh(stack):
    auth, trade, pool, redis = stack
    session = await start(auth, trade)
    same = await auth.post("/auth/demo/start", json={})
    assert same.json()["user_id"] == session["user_id"]
    assert "set-cookie" not in same.headers
    payload = await order(trade)
    first = await trade.post("/demo/orders", json=payload)
    assert first.status_code == 201, first.text
    receipt = first.json()
    assert receipt["disposition"] == "filled"
    assert receipt["fills"] == [
        {"price": 100.0, "quantity": 3},
        {"price": 100.1, "quantity": 2},
    ]
    assert receipt["after"]["cash_balance"] == pytest.approx(9499.8, abs=1e-8)
    assert receipt["after"]["holding"] == 5
    assert receipt["average_fill_price"] == pytest.approx(100.04, abs=1e-8)
    retry = await trade.post("/demo/orders", json=payload)
    assert retry.json() == receipt
    changed = await trade.post("/demo/orders", json={**payload, "quantity": 6})
    assert changed.status_code == 409
    assert (await trade.get("/demo/orders")).json()["receipts"] == [receipt]
    assert (await trade.get("/demo/orders/" + receipt["receipt_id"])).json() == receipt
    async with pool.acquire() as conn:
        persisted = await AsyncpgOrdersRepository(conn).get_order(receipt["order_id"])
        assert (
            persisted.user_id == session["user_id"]
        )  # UUID deserialization regression from open PR #1
        assert await conn.fetchval("SELECT COUNT(*) FROM orders") == 1


@pytest.mark.asyncio
async def test_two_owners_and_wrong_owner_receipt(stack):
    auth, trade, pool, redis = stack
    first = await start(auth, trade)
    response = await trade.post("/demo/orders", json=await order(trade))
    receipt_id = response.json()["receipt_id"]
    auth.cookies.clear()
    trade.cookies.clear()
    second = await start(auth, trade)
    assert second["user_id"] != first["user_id"]
    assert (await trade.get("/demo/account")).json()["account"]["cash_balance"] == 10000
    assert (await trade.get("/demo/orders/" + receipt_id)).status_code == 404
    assert (await trade.get("/demo/orders")).json()["receipts"] == []
    assert (
        await trade.post(
            "/orders",
            json={
                "instrument_id": "EQ-ACME",
                "side": "BUY",
                "quantity": 1,
                "order_type": "MARKET",
            },
        )
    ).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case,disposition,cash,holding,residual,status",
    [
        ("partial", "partially_filled_final", 9699.8, 3, 2, 201),
        ("limit", "not_filled_final", 10000, 0, 5, 201),
        ("rejection", "rejected", 10000, 0, 1, 400),
    ],
)
async def test_fixture_outcomes_and_rejection_idempotency(
    stack, case, disposition, cash, holding, residual, status
):
    auth, trade, pool, redis = stack
    await start(auth, trade)
    account = (await trade.get("/demo/account")).json()
    reset = await trade.post(
        "/demo/reset", json={"generation": account["generation"], "case_id": case}
    )
    assert reset.status_code == 200
    book = (await trade.get("/demo/book")).json()
    payload = {**await order(trade), **book["suggested_order"]}
    result = await trade.post("/demo/orders", json=payload)
    assert result.status_code == status, result.text
    receipt = result.json()
    assert receipt["disposition"] == disposition
    assert receipt["residual_quantity"] == residual
    assert receipt["after"]["cash_balance"] == pytest.approx(cash, abs=1e-8)
    assert receipt["after"]["holding"] == holding
    retry = await trade.post("/demo/orders", json=payload)
    assert retry.status_code == status and retry.json() == receipt
    if case == "rejection":
        assert receipt["before"] == receipt["after"] and not receipt["fills"]
        async with pool.acquire() as conn:
            assert await conn.fetchval("SELECT COUNT(*) FROM orders") == 0


@pytest.mark.asyncio
async def test_cash_and_sell_conservation(stack):
    auth, trade, pool, redis = stack
    await start(auth, trade)
    await trade.post("/demo/orders", json=await order(trade))
    sell_payload = {**await order(trade), "side": "SELL"}
    sell = await trade.post("/demo/orders", json=sell_payload)
    receipt = sell.json()
    assert receipt["consideration"] == pytest.approx(499.3, abs=1e-8)
    assert receipt["after"]["cash_balance"] == pytest.approx(9999.1, abs=1e-8)
    assert receipt["after"]["holding"] == 0
    assert receipt["after"]["cash_balance"] - receipt["before"][
        "cash_balance"
    ] == pytest.approx(receipt["consideration"], abs=1e-8)


@pytest.mark.asyncio
async def test_concurrent_buys_cannot_spend_same_cash(stack):
    auth, trade, pool, redis = stack
    session = await start(auth, trade)
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE accounts SET cash_balance=600 WHERE user_id=$1", session["user_id"]
        )
    payload = await order(trade)
    responses = await asyncio.gather(
        trade.post("/demo/orders", json=payload),
        trade.post("/demo/orders", json={**payload, "idempotency_key": str(uuid4())}),
    )
    assert sorted(r.status_code for r in responses) == [201, 400]
    account = (await trade.get("/demo/account")).json()["account"]
    assert (
        account["cash_balance"] == pytest.approx(99.8, abs=1e-8)
        and account["holding"] == 5
    )


@pytest.mark.asyncio
async def test_reset_race_old_generation_cannot_mutate_new_case(stack):
    auth, trade, pool, redis = stack
    await start(auth, trade)
    payload = await order(trade)
    reset = trade.post(
        "/demo/reset", json={"generation": payload["generation"], "case_id": "partial"}
    )
    submit = trade.post("/demo/orders", json=payload)
    reset_response, order_response = await asyncio.gather(reset, submit)
    assert reset_response.status_code == 200
    assert order_response.status_code in (201, 409)
    current = (await trade.get("/demo/account")).json()
    assert current["generation"] != payload["generation"]
    assert (
        current["account"]["cash_balance"] == 10000
        and current["account"]["holding"] == 0
    )
    assert (await trade.post("/demo/orders", json=payload)).status_code == 409


@pytest.mark.asyncio
async def test_failed_receipt_insert_rolls_back_all_financial_state(stack):
    auth, trade, pool, redis = stack
    await start(auth, trade)
    async with pool.acquire() as conn:
        await conn.execute(
            "CREATE FUNCTION reject_receipt() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'test rollback'; END $$; CREATE TRIGGER reject_receipt BEFORE INSERT ON demo_receipts FOR EACH ROW EXECUTE FUNCTION reject_receipt()"
        )
    try:
        result = await trade.post("/demo/orders", json=await order(trade))
        assert result.status_code == 500
        current = (await trade.get("/demo/account")).json()
        assert (
            current["account"]["cash_balance"] == 10000
            and current["account"]["holding"] == 0
        )
        async with pool.acquire() as conn:
            assert await conn.fetchval("SELECT COUNT(*) FROM orders") == 0
            assert await conn.fetchval("SELECT COUNT(*) FROM demo_receipts") == 0
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DROP TRIGGER reject_receipt ON demo_receipts; DROP FUNCTION reject_receipt()"
            )


@pytest.mark.asyncio
async def test_expiry_revocation_cross_origin_and_validation(stack):
    auth, trade, pool, redis = stack
    assert (await trade.get("/demo/account")).status_code == 401
    assert (
        await auth.post(
            "/auth/demo/start", json={}, headers={"Origin": "https://evil.test"}
        )
    ).status_code == 403
    session = await start(auth, trade)
    payload = await order(trade)
    assert (
        await trade.post(
            "/demo/orders", json=payload, headers={"Origin": "https://evil.test"}
        )
    ).status_code == 403
    assert (
        await trade.post(
            "/demo/reset",
            json={"generation": payload["generation"], "case_id": "full"},
            headers={"Origin": "https://evil.test"},
        )
    ).status_code == 403
    assert (
        await trade.post("/demo/orders", json={**payload, "instrument_id": "FUT-ES"})
    ).status_code == 422
    assert (
        await trade.post("/demo/orders", json={**payload, "quantity": 0})
    ).status_code == 422
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE demo_guests SET expires_at=NOW()-INTERVAL '1 minute' WHERE user_id=$1",
            session["user_id"],
        )
    assert (await trade.get("/demo/account")).status_code == 401
    auth.cookies.clear()
    trade.cookies.clear()
    await start(auth, trade)
    logout = await auth.post("/auth/logout")
    assert logout.status_code == 204 and "Max-Age=0" in logout.headers["set-cookie"]
    assert (await trade.get("/demo/account")).status_code == 401


@pytest.mark.asyncio
async def test_guest_password_login_forbidden_and_throttle(stack):
    auth, trade, pool, redis = stack
    session = await start(auth, trade)
    result = await auth.post(
        "/auth/login",
        json={
            "email": session["user_id"] + "@demo.invalid",
            "password": "!guest-login-disabled",
        },
    )
    assert result.status_code == 401
    for _ in range(4):
        auth.cookies.clear()
        trade.cookies.clear()
        await start(auth, trade)
    auth.cookies.clear()
    result = await auth.post("/auth/demo/start", json={})
    assert result.status_code == 429 and result.headers["retry-after"] == "60"


@pytest.mark.asyncio
async def test_migration_preserves_old_rows_and_is_repeatable(stack):
    auth, trade, pool, redis = stack
    async with pool.acquire() as conn:
        await conn.execute(
            "CREATE SCHEMA upgrade_test; CREATE TABLE upgrade_test.users(id UUID PRIMARY KEY,email TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,created_at TIMESTAMPTZ DEFAULT NOW())"
        )
        await conn.execute(
            "INSERT INTO upgrade_test.users(id,email,password_hash) VALUES($1,'old@example.test','old')",
            uuid4(),
        )
    try:
        await prepare_schema(pool, "upgrade_test")
        await prepare_schema(pool, "upgrade_test")
        async with pool.acquire() as conn:
            assert (
                await conn.fetchval(
                    "SELECT principal_kind FROM upgrade_test.users WHERE email='old@example.test'"
                )
                == "registered"
            )
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DROP SCHEMA upgrade_test CASCADE")


@pytest.mark.asyncio
async def test_retention_only_old_guest_owners_and_session_budgets(stack):
    from pathlib import Path

    auth, trade, pool, redis = stack
    guest = await start(auth, trade)
    await trade.post("/demo/orders", json=await order(trade))
    async with pool.acquire() as conn:
        regular = await conn.fetchval(
            "SELECT id FROM users WHERE principal_kind='registered'"
        )
        # Even an inconsistent guest marker must never make an ordinary account eligible.
        await conn.execute(
            "INSERT INTO demo_guests(user_id,expires_at) VALUES($1,NOW()-INTERVAL '3 days')",
            regular,
        )
        await conn.execute(
            "INSERT INTO demo_cases(user_id,generation,case_id) VALUES($1,$2,'full')",
            regular,
            uuid4(),
        )
        await conn.execute(
            "UPDATE demo_cases SET submissions=100,resets=20 WHERE user_id=$1",
            guest["user_id"],
        )
    assert (
        await trade.post("/demo/orders", json=await order(trade))
    ).status_code == 429
    account = (await trade.get("/demo/account")).json()
    assert (
        await trade.post(
            "/demo/reset", json={"generation": account["generation"], "case_id": "full"}
        )
    ).status_code == 429
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE demo_guests SET expires_at=NOW()-INTERVAL '25 hours' WHERE user_id=$1",
            guest["user_id"],
        )
        await conn.execute(Path("deploy/02_demo_guest_retention.sql").read_text())
        assert await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM users WHERE id=$1)", regular
        )
        assert not await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM users WHERE id=$1)", guest["user_id"]
        )
        assert await conn.fetchval("SELECT COUNT(*) FROM demo_receipts") == 0
        assert await conn.fetchval("SELECT COUNT(*) FROM orders") == 0


@pytest.mark.asyncio
async def test_global_guest_cap_and_redis_expiry(stack, monkeypatch):
    import auth.demo as guest_module

    auth, trade, pool, redis = stack
    monkeypatch.setattr(guest_module, "DEMO_MAX_GUESTS", 1)
    await start(auth, trade)
    token = trade.cookies.get("session_id")
    await redis.delete("auth_session:" + token)
    assert (await trade.get("/demo/account")).status_code == 401
    auth.cookies.clear()
    trade.cookies.clear()
    response = await auth.post("/auth/demo/start", json={})
    assert response.status_code == 503
