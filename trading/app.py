from __future__ import annotations

import uuid
from datetime import datetime, timezone

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, status
from redis.asyncio import Redis
from common.logging import configure_structured_logging, get_logger

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


def create_app(
    *,
    order_service: OrderService,
    market_data_gateway: MarketDataGateway,
) -> FastAPI:
    app = FastAPI(title="Trading Agent API")

    async def get_order_service() -> OrderService:
        return order_service

    async def get_market_data_gateway() -> MarketDataGateway:
        return market_data_gateway

    @app.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
    async def create_order_endpoint(
        request: OrderCreateRequest,
        service: OrderService = Depends(get_order_service),
        data_gateway: MarketDataGateway = Depends(get_market_data_gateway),
    ) -> OrderResponse:
        try:
            order_book = await data_gateway.get_order_book(request.instrument_id)
            order = await service.submit(request.to_domain_request(), order_book)
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

    matching_engine = MatchingEngine()
    pool: asyncpg.Pool | None = None
    redis_client: Redis | None = None
    order_service: OrderService | None = None
    market_data_provider: MarketDataGateway | None = None

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
        nonlocal pool, redis_client, order_service, market_data_provider
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
        request: OrderCreateRequest,
        service: OrderService = Depends(get_order_service),
        data_gateway: MarketDataGateway = Depends(get_market_data_gateway),
    ) -> OrderResponse:
        try:
            order_book = await data_gateway.get_order_book(request.instrument_id)
            order = await service.submit(request.to_domain_request(), order_book)
        except InstrumentNotFoundError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="instrument not found") from None
        except InsufficientBalanceError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except InsufficientPositionError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except OrderValidationError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return OrderResponse.from_domain(order)

    @app.get("/health", status_code=status.HTTP_200_OK)
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    return app
