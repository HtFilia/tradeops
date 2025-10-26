from __future__ import annotations

import os
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.e2e


RUN_E2E = os.getenv("RUN_E2E_TESTS") == "1"

if not RUN_E2E:  # pragma: no cover - guarded for local runs
    pytest.skip("E2E tests require RUN_E2E_TESTS=1", allow_module_level=True)


AUTH_URL = os.getenv("E2E_AUTH_URL", "http://localhost:8082")
TRADING_URL = os.getenv("E2E_TRADING_URL", "http://localhost:8081")
MARKET_URL = os.getenv("E2E_MARKET_URL", "http://localhost:8080")


@pytest.mark.asyncio
async def test_end_to_end_order_flow() -> None:
    async with AsyncClient() as client:
        # Ensure auth responds and log in with demo credentials (seeded by startup)
        login_response = await client.post(
            f"{AUTH_URL}/auth/login",
            json={"email": "demo@example.com", "password": "demo"},
        )
        assert login_response.status_code == 200
        session_cookie = client.cookies.get("session_id")
        assert session_cookie

        session_response = await client.get(f"{AUTH_URL}/auth/session")
        assert session_response.status_code == 200
        user_id = session_response.json()["user_id"]
        assert user_id

        # Fetch market data snapshot
        market_response = await client.get(f"{MARKET_URL}/health")
        assert market_response.status_code == 200
        instruments = market_response.json()["instruments"]
        assert "EQ-ACME" in instruments

        # Place an order via trading agent
        order_payload = {
            "instrument_id": "EQ-ACME",
            "side": "BUY",
            "quantity": 10,
            "order_type": "MARKET",
        }
        order_response = await client.post(f"{TRADING_URL}/orders", json=order_payload)
        assert order_response.status_code == 201
        body = order_response.json()
        assert body["status"] in {"FILLED", "PARTIALLY_FILLED", "NEW"}
        assert body["instrument_id"] == order_payload["instrument_id"]

        # Logout to ensure session revocation works
        logout_response = await client.post(f"{AUTH_URL}/auth/logout")
        assert logout_response.status_code == 204

        # Session endpoint should now reject
        post_logout = await client.get(f"{AUTH_URL}/auth/session")
        assert post_logout.status_code == 401
