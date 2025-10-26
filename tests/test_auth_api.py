from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("argon2")
pytest.importorskip("redis.asyncio")

from httpx import ASGITransport, AsyncClient

from auth.app import create_auth_app
from auth.configuration import AuthConfig
from auth.constants import SESSION_COOKIE_NAME
from auth.models import RegistrationRequest
from tests.auth_stubs import StubAccount, StubSession, StubUser

pytestmark = pytest.mark.integration

@pytest.fixture
def auth_config() -> AuthConfig:
    return AuthConfig(
        starting_balance=Decimal("500000"),
        base_currency="USD",
        session_ttl_minutes=60,
    )


@pytest.fixture
def stub_dependencies(auth_config: AuthConfig) -> tuple[StubUser, StubAccount, StubSession]:
    return (
        StubUser(),
        StubAccount(),
        StubSession(ttl=timedelta(minutes=auth_config.session_ttl_minutes)),
    )


def build_app(deps: tuple[StubUser, StubAccount, StubSession], config: AuthConfig):
    user_repo, account_repo, session_store = deps
    return create_auth_app(
        user_repository=user_repo,
        account_repository=account_repo,
        session_store=session_store,
        config=config,
    )


@pytest.mark.asyncio
async def test_register_endpoint_returns_session_cookie(stub_dependencies, auth_config: AuthConfig) -> None:
    app = build_app(stub_dependencies, auth_config)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/auth/register",
            json={"email": "frank@example.com", "password": "Val1dPass!"},
        )

    assert response.status_code == 201
    assert response.json()["user_id"].startswith("user-")
    cookie_value = response.cookies.get(SESSION_COOKIE_NAME)
    assert cookie_value is not None
    assert cookie_value.startswith("session-")


@pytest.mark.asyncio
async def test_register_endpoint_rejects_duplicates(stub_dependencies, auth_config: AuthConfig) -> None:
    user_repo, _, _ = stub_dependencies
    existing_session = await build_app(stub_dependencies, auth_config).state.auth_service.register_user(
        RegistrationRequest(email="george@example.com", password="Inv1teOnly!")
    )
    app = build_app(stub_dependencies, auth_config)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/auth/register",
            json={"email": "george@example.com", "password": "Inv1teOnly!"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Email already registered"

    # Ensure previous session remains intact
    assert existing_session.token.value.startswith("session-")


@pytest.mark.asyncio
async def test_login_endpoint_sets_cookie(stub_dependencies, auth_config: AuthConfig) -> None:
    app = build_app(stub_dependencies, auth_config)
    service = app.state.auth_service
    await service.register_user(RegistrationRequest(email="hannah@example.com", password="Sup3rStrong!"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/auth/login",
            json={"email": "hannah@example.com", "password": "Sup3rStrong!"},
        )

    assert response.status_code == 200
    assert response.json()["user_id"].startswith("user-")
    assert response.cookies.get(SESSION_COOKIE_NAME) is not None


@pytest.mark.asyncio
async def test_login_endpoint_rejects_invalid_credentials(stub_dependencies, auth_config: AuthConfig) -> None:
    app = build_app(stub_dependencies, auth_config)
    service = app.state.auth_service
    await service.register_user(RegistrationRequest(email="ivan@example.com", password="Y3tAn0ther!"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/auth/login",
            json={"email": "ivan@example.com", "password": "WrongPass123"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_logout_endpoint_clears_cookie(stub_dependencies, auth_config: AuthConfig) -> None:
    app = build_app(stub_dependencies, auth_config)
    service = app.state.auth_service
    session = await service.register_user(RegistrationRequest(email="jane@example.com", password="Log0utTest!"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        client.cookies.set(SESSION_COOKIE_NAME, session.token.value)
        response = await client.post("/auth/logout")

    assert response.status_code == 204
    assert response.cookies.get(SESSION_COOKIE_NAME) is None


@pytest.mark.asyncio
async def test_session_endpoint_returns_current_user(stub_dependencies, auth_config: AuthConfig) -> None:
    app = build_app(stub_dependencies, auth_config)
    service = app.state.auth_service
    session = await service.register_user(RegistrationRequest(email="karl@example.com", password="Sess!0nTest"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        client.cookies.set(SESSION_COOKIE_NAME, session.token.value)
        response = await client.get("/auth/session")

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == session.user_id
