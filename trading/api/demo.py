from typing import Awaitable, Callable, TypeVar
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from common.demo_limits import require_same_origin
from trading.domain.demo import DemoOrderInput, DemoResetInput
from trading.services.demo_service import DemoService, DemoError, Receipt


T = TypeVar("T")


def demo_router(
    service_provider: Callable[[], DemoService],
    owner_resolver: Callable[[Request], Awaitable[str]],
    reset_guard: Callable[[Request], Awaitable[None]],
    origins: list[str],
) -> APIRouter:
    router = APIRouter(prefix="/demo", tags=["isolated snapshot demo"])

    async def current_owner(request: Request) -> str:
        return await owner_resolver(request)

    async def invoke(operation: Awaitable[T]) -> T:
        try:
            return await operation
        except DemoError as exc:
            raise HTTPException(exc.status, str(exc)) from exc

    @router.get("/account")
    async def account(owner: str = Depends(current_owner)) -> dict[str, object]:
        return await invoke(service_provider().account(owner))

    @router.get("/book")
    async def book(owner: str = Depends(current_owner)) -> dict[str, object]:
        return await invoke(service_provider().book(owner))

    @router.get("/orders")
    async def history(
        owner: str = Depends(current_owner),
        limit: int = Query(20, ge=1, le=50),
        offset: int = Query(0, ge=0, le=1000),
    ) -> dict[str, object]:
        return await invoke(service_provider().history(owner, limit, offset))

    @router.get("/orders/{receipt_id}", response_model=Receipt)
    async def receipt(receipt_id: UUID, owner: str = Depends(current_owner)) -> Receipt:
        return await invoke(service_provider().receipt(owner, receipt_id))

    @router.post("/reset")
    async def reset(
        request: Request, body: DemoResetInput, owner: str = Depends(current_owner)
    ) -> dict[str, object]:
        require_same_origin(request, origins)
        await reset_guard(request)
        return await invoke(service_provider().reset(owner, body))

    @router.post("/orders", response_model=Receipt)
    async def submit(
        request: Request, body: DemoOrderInput, owner: str = Depends(current_owner)
    ) -> JSONResponse:
        require_same_origin(request, origins)
        result = await invoke(service_provider().submit(owner, body))
        return JSONResponse(
            status_code=400 if result.disposition == "rejected" else 201,
            content=result.model_dump(mode="json"),
        )

    return router
