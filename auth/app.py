from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response, status

from auth.configuration import AuthConfig
from auth.models import LoginRequest, RegistrationRequest, SessionResponse
from auth.service import AuthService, InvalidCredentialsError, UserAlreadyExistsError
from auth.session import SessionStore, SessionToken
from auth.storage import AccountRepository, UserRepository


def create_auth_app(
    *,
    user_repository: UserRepository,
    account_repository: AccountRepository,
    session_store: SessionStore,
    config: AuthConfig,
) -> FastAPI:
    """Return a configured FastAPI application for the Auth agent."""
    app = FastAPI(title="Auth & User Management Agent", version="0.1.0")
    service = AuthService(
        user_repository=user_repository,
        account_repository=account_repository,
        session_store=session_store,
        config=config,
    )

    app.state.auth_service = service  # type: ignore[attr-defined]
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post(
        "/register",
        response_model=SessionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def register_user(request: RegistrationRequest, response: Response) -> SessionResponse:
        try:
            session = await service.register_user(request)
        except UserAlreadyExistsError:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered") from None

        _set_session_cookie(response, session.token, session.expires_at, config)
        return SessionResponse(user_id=session.user_id, expires_at=session.expires_at)

    @router.post(
        "/login",
        response_model=SessionResponse,
        status_code=status.HTTP_200_OK,
    )
    async def login_user(request: LoginRequest, response: Response) -> SessionResponse:
        try:
            session = await service.login_user(request)
        except InvalidCredentialsError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials") from None

        _set_session_cookie(response, session.token, session.expires_at, config)
        return SessionResponse(user_id=session.user_id, expires_at=session.expires_at)

    @router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
    async def logout_user(request: Request, response: Response) -> Response:
        raw_token = request.cookies.get(config.session_cookie_name, "")
        if raw_token:
            await service.logout_user(SessionToken(value=raw_token))
        _clear_session_cookie(response, config)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    app.include_router(router)
    return app


def _set_session_cookie(
    response: Response,
    token: SessionToken,
    expires_at: datetime,
    config: AuthConfig,
) -> None:
    ttl_seconds = config.session_ttl_minutes * 60
    response.set_cookie(
        key=config.session_cookie_name,
        value=token.value,
        max_age=ttl_seconds,
        expires=expires_at,
        httponly=True,
        secure=config.secure_cookies,
        samesite="lax",
        domain=config.session_cookie_domain,
        path="/",
    )


def _clear_session_cookie(response: Response, config: AuthConfig) -> None:
    response.delete_cookie(
        key=config.session_cookie_name,
        domain=config.session_cookie_domain,
        path="/",
    )


__all__ = ["create_auth_app"]
