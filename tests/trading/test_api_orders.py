from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from auth.models import AuthenticatedSession
from auth.session import SessionToken
from fastapi import HTTPException, Request, status
from tests.trading.in_memory import (
    InMemoryExecutionPublisher,
    InMemoryTradingUnitOfWork,
)
from trading.app import create_app
from trading.domain.matching import MatchingEngine
from trading.domain.models import ListedInstrumentBook
from trading.ports.market_data import MarketDataGateway
from trading.services.order_service import OrderService

pytestmark = pytest.mark.integration

class StaticMarketDataGateway(MarketDataGateway):
    def __init__(self, book: ListedInstrumentBook) -> None:
        self._book = book

    async def get_order_book(self, instrument_id: str) -> ListedInstrumentBook:
        return self._book


def build_app() -> tuple:
    book = ListedInstrumentBook(
        instrument_id="instr-abc",
        bids=[(99.5, 100), (99.0, 200)],
        asks=[(100.5, 150), (101.0, 100)],
        last_updated=datetime.now(tz=timezone.utc),
    )
    service = OrderService(
        uow_factory=InMemoryTradingUnitOfWork,
        matching_engine=MatchingEngine(),
        execution_publisher=InMemoryExecutionPublisher(published=[]),
        id_generator=lambda: "order-001",
        clock=lambda: datetime.now(tz=timezone.utc),
    )
    async def fake_session_resolver(_: Request) -> AuthenticatedSession:
        return AuthenticatedSession(
            token=SessionToken("session-token"),
            user_id="user-123",
            expires_at=datetime.now(tz=timezone.utc),
        )

    app = create_app(
        order_service=service,
        market_data_gateway=StaticMarketDataGateway(book),
        session_resolver=fake_session_resolver,
        cors_origins=["http://test"],
    )
    return app, service


@pytest.mark.asyncio
async def test_create_order_endpoint_executes_order() -> None:
    app, service = build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "instrument_id": "instr-abc",
            "side": "BUY",
            "quantity": 100,
            "order_type": "MARKET",
        }
        response = await client.post("/orders", json=payload)
        assert response.status_code == 201
        body = response.json()
        assert body["order_id"] == "order-001"
        assert body["status"] == "FILLED"
        assert body["filled_quantity"] == 100


@pytest.mark.asyncio
async def test_create_order_requires_session() -> None:
    book = ListedInstrumentBook(
        instrument_id="instr-abc",
        bids=[(99.5, 100)],
        asks=[(101.0, 100)],
        last_updated=datetime.now(tz=timezone.utc),
    )
    service = OrderService(
        uow_factory=InMemoryTradingUnitOfWork,
        matching_engine=MatchingEngine(),
        execution_publisher=InMemoryExecutionPublisher(published=[]),
        id_generator=lambda: "order-001",
        clock=lambda: datetime.now(tz=timezone.utc),
    )

    async def rejecting_resolver(_: Request) -> AuthenticatedSession:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    app = create_app(
        order_service=service,
        market_data_gateway=StaticMarketDataGateway(book),
        session_resolver=rejecting_resolver,
        cors_origins=["http://test"],
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/orders",
            json={
                "instrument_id": "instr-abc",
                "side": "BUY",
                "quantity": 10,
                "order_type": "MARKET",
            },
        )

    assert response.status_code == 401
