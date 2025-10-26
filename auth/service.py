from __future__ import annotations

from dataclasses import dataclass

from auth.models import AuthenticatedSession, LoginRequest, RegistrationRequest
from auth.security import Argon2PasswordHasher
from auth.session import SessionStore, SessionToken
from auth.storage import AccountRepository, UserRepository
from auth.configuration import AuthConfig


@dataclass(slots=True)
class UserAlreadyExistsError(Exception):
    email: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"User already exists for email={self.email}"


class InvalidCredentialsError(Exception):
    """Raised when login credentials are incorrect."""


class AuthService:
    """Domain service orchestrating registration, login, and session management."""

    def __init__(
        self,
        user_repository: UserRepository,
        account_repository: AccountRepository,
        session_store: SessionStore,
        config: AuthConfig,
        password_hasher: Argon2PasswordHasher | None = None,
    ) -> None:
        self._user_repository = user_repository
        self._account_repository = account_repository
        self._session_store = session_store
        self._config = config
        self._password_hasher = password_hasher or Argon2PasswordHasher()

    async def register_user(self, request: RegistrationRequest) -> AuthenticatedSession:
        existing = await self._user_repository.get_by_email(request.email)
        if existing is not None:
            raise UserAlreadyExistsError(email=request.email)

        password_hash = self._password_hasher.hash(request.password)
        user = await self._user_repository.create(request.email, password_hash)
        await self._account_repository.create_account(
            user_id=user.id,
            starting_balance=self._config.starting_balance,
            currency=self._config.base_currency,
        )
        return await self._session_store.issue(user.id)

    async def login_user(self, request: LoginRequest) -> AuthenticatedSession:
        user = await self._user_repository.get_by_email(request.email)
        if user is None or not self._password_hasher.verify(user.password_hash, request.password):
            raise InvalidCredentialsError("Invalid credentials")
        return await self._session_store.issue(user.id)

    async def logout_user(self, token: SessionToken) -> None:
        await self._session_store.revoke(token)


__all__ = ["AuthService", "InvalidCredentialsError", "UserAlreadyExistsError"]
