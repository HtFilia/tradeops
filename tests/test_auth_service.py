from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

pytest.importorskip("argon2")
pytest.importorskip("redis.asyncio")

from auth.configuration import AuthConfig
from auth.models import LoginRequest, RegistrationRequest, User
from auth.service import AuthService, UserAlreadyExistsError, InvalidCredentialsError
from tests.auth_stubs import StubAccount, StubSession, StubUser


@pytest.fixture
def config() -> AuthConfig:
    return AuthConfig(
        starting_balance=Decimal("1000000"),
        base_currency="USD",
        session_ttl_minutes=30,
    )


@pytest.mark.asyncio
async def test_register_user_creates_account_and_issues_session(config: AuthConfig) -> None:
    user_repo = StubUser()
    account_repo = StubAccount()
    session_store = StubSession(ttl=timedelta(minutes=config.session_ttl_minutes))
    service = AuthService(user_repository=user_repo, account_repository=account_repo, session_store=session_store, config=config)

    request = RegistrationRequest(email="alice@example.com", password="Secur3!pass")
    session = await service.register_user(request)

    assert len(user_repo.created) == 1
    created_user = user_repo.created[0]
    assert created_user.email == "alice@example.com"
    assert created_user.password_hash != request.password
    assert created_user.password_hash.startswith("$argon2")

    assert account_repo.created_accounts == [
        (created_user.id, Decimal("1000000"), "USD", False),
    ]
    assert session.user_id == created_user.id
    assert session.token.value.startswith("session-")
    assert session in session_store.issued


@pytest.mark.asyncio
async def test_register_rejects_duplicate_emails(config: AuthConfig) -> None:
    user_repo = StubUser()
    account_repo = StubAccount()
    session_store = StubSession(ttl=timedelta(minutes=config.session_ttl_minutes))
    service = AuthService(user_repository=user_repo, account_repository=account_repo, session_store=session_store, config=config)

    existing_user = User(
        id="user-1",
        email="bob@example.com",
        password_hash="$argon2$dummy",
        created_at=datetime.now(timezone.utc),
    )
    user_repo.existing[existing_user.email] = existing_user

    request = RegistrationRequest(email="bob@example.com", password="Password123!")
    with pytest.raises(UserAlreadyExistsError):
        await service.register_user(request)

    assert account_repo.created_accounts == []
    assert not session_store.issued


@pytest.mark.asyncio
async def test_login_validates_password_and_returns_session(config: AuthConfig) -> None:
    user_repo = StubUser()
    account_repo = StubAccount()
    session_store = StubSession(ttl=timedelta(minutes=config.session_ttl_minutes))
    service = AuthService(user_repository=user_repo, account_repository=account_repo, session_store=session_store, config=config)

    register_request = RegistrationRequest(email="carol@example.com", password="Sup3rSecret!")
    session = await service.register_user(register_request)

    login_request = LoginRequest(email="carol@example.com", password="Sup3rSecret!")
    login_session = await service.login_user(login_request)

    assert login_session.user_id == session.user_id
    assert len(session_store.issued) == 2  # register + login


@pytest.mark.asyncio
async def test_login_rejects_invalid_password(config: AuthConfig) -> None:
    user_repo = StubUser()
    account_repo = StubAccount()
    session_store = StubSession(ttl=timedelta(minutes=config.session_ttl_minutes))
    service = AuthService(user_repository=user_repo, account_repository=account_repo, session_store=session_store, config=config)

    await service.register_user(RegistrationRequest(email="dana@example.com", password="StrongPass!1"))

    bad_request = LoginRequest(email="dana@example.com", password="BadPass123")
    with pytest.raises(InvalidCredentialsError):
        await service.login_user(bad_request)


@pytest.mark.asyncio
async def test_logout_revokes_session(config: AuthConfig) -> None:
    user_repo = StubUser()
    account_repo = StubAccount()
    session_store = StubSession(ttl=timedelta(minutes=config.session_ttl_minutes))
    service = AuthService(user_repository=user_repo, account_repository=account_repo, session_store=session_store, config=config)

    session = await service.register_user(RegistrationRequest(email="ed@example.com", password="T0ughPass!"))
    await service.logout_user(session.token)

    assert session_store.revoked_tokens == [session.token]
    assert await session_store.get(session.token) == session
