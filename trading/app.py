from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from common.logging import configure_structured_logging

from auth.models import AuthenticatedSession
from auth.session import RedisSessionStore, SessionToken

from trading.api.schemas import OrderCreateRequest, OrderResponse
from trading.config import TradingSettings, load_settings
from trading.domain.exceptions import (
    InsufficientBalanceError,
    InsufficientPositionError,
    InstrumentNotFoundError,
    OrderValidationError,
)
from trading.domain.matching import MatchingEngine
from trading.infrastructure.events import RedisExecutionPublisher
from trading.infrastructure.market_data import RedisMarketDataGateway
from trading.infrastructure.uow import AsyncpgTradingUnitOfWork
from trading.ports.market_data import MarketDataGateway
from trading.ports.repositories import TradingUnitOfWork
from trading.services.order_service import OrderService

logger = configure_structured_logging("trading.app")

SessionResolver = Callable[[Request], Awaitable[AuthenticatedSession]]


def create_app(
    *,
    order_service: OrderService,
    market_data_gateway: MarketDataGateway,
    session_resolver: SessionResolver | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    app = FastAPI(title="Trading Agent API")

    origins = list(cors_origins or ["http://localhost:5173"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    async def get_order_service() -> OrderService:
        return order_service

    async def get_market_data_gateway() -> MarketDataGateway:
        return market_data_gateway

    if session_resolver is None:

        async def _missing_session_resolver(_: Request) -> AuthenticatedSession:  # pragma: no cover - defensive guard
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Session resolver not configured",
            )

        session_resolver = _missing_session_resolver

    async def get_current_session(request: Request) -> AuthenticatedSession:
        return await session_resolver(request)

    @app.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
    async def create_order_endpoint(
        request: OrderCreateRequest,
        service: OrderService = Depends(get_order_service),
        data_gateway: MarketDataGateway = Depends(get_market_data_gateway),
        session: AuthenticatedSession = Depends(get_current_session),
    ) -> OrderResponse:
        try:
            order_book = await data_gateway.get_order_book(request.instrument_id)
            order = await service.submit(request.to_domain_request(session.user_id), order_book)
        except InstrumentNotFoundError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="instrument not found") from None
        except InsufficientBalanceError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except InsufficientPositionError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except OrderValidationError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        response = OrderResponse.from_domain(order)
        logger.info(
            "Order created successfully",
            extra={
                "event": "trading.order.created",
                "context": {
                    "order_id": response.order_id,
                    "instrument_id": response.instrument_id,
                    "side": response.side.value,
                    "status": response.status.value,
                    "filled_quantity": response.filled_quantity,
                },
            },
        )
        return response

    @app.get("/health", status_code=status.HTTP_200_OK)
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    return app


def create_default_app(settings: TradingSettings | None = None) -> FastAPI:
    resolved_settings = settings or load_settings()
    app = FastAPI(title="Trading Agent API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    matching_engine = MatchingEngine()
    pool: asyncpg.Pool | None = None
    redis_client: Redis | None = None
    order_service: OrderService | None = None
    market_data_provider: MarketDataGateway | None = None
    session_store: RedisSessionStore | None = None

    def id_generator() -> str:
        return uuid.uuid4().hex

    def clock() -> datetime:
        return datetime.now(tz=timezone.utc)

    def make_uow() -> TradingUnitOfWork:
        if pool is None:
            raise RuntimeError("database connection not initialised")
        return AsyncpgTradingUnitOfWork(pool=pool)

    async def get_order_service() -> OrderService:
        if order_service is None:
            raise RuntimeError("order service not initialised")
        return order_service

    async def get_market_data_gateway() -> MarketDataGateway:
        if market_data_provider is None:
            raise RuntimeError("market data gateway not ready")
        return market_data_provider

    @app.on_event("startup")
    async def on_startup() -> None:
        nonlocal pool, redis_client, order_service, market_data_provider, session_store
        pool = await asyncpg.create_pool(dsn=resolved_settings.postgres_dsn)
        redis_client = Redis.from_url(resolved_settings.redis_url)
        execution_publisher = RedisExecutionPublisher(
            client=redis_client,
            stream=resolved_settings.execution_stream,
        )
        market_data_provider = RedisMarketDataGateway(
            client=redis_client,
            book_prefix="marketdata:book",
        )
        session_store = RedisSessionStore(
            redis=redis_client,
            ttl=resolved_settings.session_ttl,
        )
        order_service = OrderService(
            uow_factory=make_uow,
            matching_engine=matching_engine,
            execution_publisher=execution_publisher,
            id_generator=id_generator,
            clock=clock,
        )
        logger.info(
            "Trading agent started",
            extra={
                "event": "trading.app.startup",
                "context": {
                    "redis_url": resolved_settings.redis_url,
                    "postgres_dsn": resolved_settings.postgres_dsn,
                    "execution_stream": resolved_settings.execution_stream,
                },
            },
        )

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        if pool is not None:
            await pool.close()
        if redis_client is not None:
            await redis_client.aclose()
        logger.info("Trading agent shut down", extra={"event": "trading.app.shutdown"})

    @app.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
    async def create_order_endpoint(
        http_request: Request,
        request: OrderCreateRequest,
        service: OrderService = Depends(get_order_service),
        data_gateway: MarketDataGateway = Depends(get_market_data_gateway),
    ) -> OrderResponse:
        if session_store is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Session store not initialised",
            )
        token_value = http_request.cookies.get(resolved_settings.session_cookie_name)
        if not token_value:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        session = await session_store.get(SessionToken(token_value))
        if session is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        try:
            order_book = await data_gateway.get_order_book(request.instrument_id)
            order = await service.submit(request.to_domain_request(session.user_id), order_book)
        except InstrumentNotFoundError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="instrument not found") from None
        except InsufficientBalanceError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except InsufficientPositionError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except OrderValidationError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        response = OrderResponse.from_domain(order)
        logger.info(
            "Order created successfully",
            extra={
                "event": "trading.order.created",
                "context": {
                    "order_id": response.order_id,
                    "instrument_id": response.instrument_id,
                    "side": response.side.value,
                    "status": response.status.value,
                    "filled_quantity": response.filled_quantity,
                },
            },
        )
        return response

    @app.get("/health", status_code=status.HTTP_200_OK)
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    return app
