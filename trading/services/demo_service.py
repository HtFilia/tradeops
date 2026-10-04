"""Owned snapshot execution. One PostgreSQL commit precedes every receipt response."""

from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Literal
from uuid import UUID, uuid4
import asyncpg
from pydantic import BaseModel
from common.demo_limits import DEMO_MAX_SUBMISSIONS, DEMO_MAX_RESETS
from trading.domain.demo import CASES, FIXTURE_VERSION, DemoOrderInput, DemoResetInput
from trading.domain.execution import prepare_execution
from trading.domain.exceptions import (
    InsufficientBalanceError,
    InsufficientPositionError,
)
from trading.domain.matching import MatchingEngine
from trading.domain.models import OrderRecord
from trading.infrastructure.uow import (
    AsyncpgAccountsRepository,
    AsyncpgPositionsRepository,
    AsyncpgOrdersRepository,
)


class DemoError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class AccountValues(BaseModel):
    cash_balance: float
    currency: str
    holding: int
    average_cost: float | None


class FillDetail(BaseModel):
    price: float
    quantity: int


class Receipt(BaseModel):
    schema_version: Literal["execution-receipt-v1"] = "execution-receipt-v1"
    receipt_id: UUID
    order_id: str | None
    generation: UUID
    case_id: str
    snapshot_id: str
    fixture_version: str
    submitted: DemoOrderInput
    disposition: Literal[
        "filled", "partially_filled_final", "not_filled_final", "rejected"
    ]
    legacy_status: str | None
    reason: str | None
    fills: list[FillDetail]
    filled_quantity: int
    residual_quantity: int
    consideration: float
    average_fill_price: float | None
    before: AccountValues
    after: AccountValues
    book: dict[str, object]
    recorded_at: datetime
    conventions: str


CONVENTIONS = (
    "Synthetic USD equity, long only, no fees/margin. Fill consideration = sum(price × quantity). "
    "Buys use weighted average cost; sells retain existing average cost. Sell requests exceeding holdings "
    "are rejected in full. Each submission reuses an immutable fixture snapshot without consuming "
    "shared liquidity. Residual quantity is final, never monitored. PostgreSQL evidence; no Redis delivery claim."
)


class DemoService:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self.engine = MatchingEngine()

    async def _lock(self, conn: asyncpg.Connection, owner: str) -> asyncpg.Record:
        case = await conn.fetchrow(
            "SELECT c.*,g.expires_at FROM demo_cases c JOIN demo_guests g USING(user_id) "
            "WHERE c.user_id=$1 AND g.expires_at>NOW() FOR UPDATE OF c",
            owner,
        )
        if case is None:
            raise DemoError(
                401, "Demo session expired or unavailable. Start a new simulation."
            )
        await conn.fetchrow(
            "SELECT user_id FROM accounts WHERE user_id=$1 FOR UPDATE", owner
        )
        return case

    async def _values(self, conn: asyncpg.Connection, owner: str) -> AccountValues:
        account = await AsyncpgAccountsRepository(conn).get_account(owner)
        position = await AsyncpgPositionsRepository(conn).get_position(owner, "EQ-ACME")
        if account is None:
            raise DemoError(409, "Demo account unavailable")
        return AccountValues(
            cash_balance=account.cash_balance,
            currency=account.base_currency,
            holding=position.quantity if position else 0,
            average_cost=position.average_price
            if position and position.quantity
            else None,
        )

    @staticmethod
    def _snapshot(case: asyncpg.Record) -> str:
        return f"{FIXTURE_VERSION}:{case['case_id']}:{case['generation']}"

    async def _summary(
        self, conn: asyncpg.Connection, owner: str, case: asyncpg.Record
    ) -> dict[str, object]:
        return dict(
            generation=str(case["generation"]),
            case_id=case["case_id"],
            expires_at=case["expires_at"].isoformat(),
            account=(await self._values(conn, owner)).model_dump(),
            remaining_submissions=DEMO_MAX_SUBMISSIONS - case["submissions"],
            remaining_resets=DEMO_MAX_RESETS - case["resets"],
            conventions=CONVENTIONS,
        )

    async def account(self, owner: str) -> dict[str, object]:
        async with self.pool.acquire() as conn, conn.transaction():
            case = await self._lock(conn, owner)
            result = await self._summary(conn, owner, case)
        return result

    async def book(self, owner: str) -> dict[str, object]:
        async with self.pool.acquire() as conn, conn.transaction():
            case = await self._lock(conn, owner)
            fixture = CASES[case["case_id"]]
            return dict(
                generation=str(case["generation"]),
                case_id=case["case_id"],
                snapshot_id=self._snapshot(case),
                fixture_version=FIXTURE_VERSION,
                source="Versioned immutable synthetic fixture",
                book=fixture.book.model_dump(mode="json"),
                suggested_order=fixture.action,
                cases=[
                    dict(case_id=k, name=v.name, description=v.description)
                    for k, v in CASES.items()
                ],
            )

    async def reset(self, owner: str, request: DemoResetInput) -> dict[str, object]:
        async with self.pool.acquire() as conn, conn.transaction():
            case = await self._lock(conn, owner)
            if case["generation"] != request.generation:
                raise DemoError(409, "Case changed. Reload before resetting.")
            if case["resets"] >= DEMO_MAX_RESETS:
                raise DemoError(
                    429, "Session reset limit reached. Start again after expiry."
                )
            await conn.execute(
                "UPDATE demo_cases SET generation=$2,case_id=$3,resets=resets+1 WHERE user_id=$1",
                owner,
                uuid4(),
                request.case_id,
            )
            await conn.execute(
                "UPDATE accounts SET cash_balance=10000,updated_at=NOW() WHERE user_id=$1",
                owner,
            )
            await conn.execute("DELETE FROM positions WHERE user_id=$1", owner)
            case = await self._lock(conn, owner)
            result = await self._summary(conn, owner, case)
        return result

    async def submit(self, owner: str, request: DemoOrderInput) -> Receipt:
        payload = request.model_dump_json()
        digest = sha256(payload.encode()).hexdigest()
        async with self.pool.acquire() as conn, conn.transaction():
            case = await self._lock(conn, owner)
            if case[
                "generation"
            ] != request.generation or request.snapshot_id != self._snapshot(case):
                raise DemoError(
                    409, "Case/snapshot changed. Reload and review the order."
                )
            prior = await conn.fetchrow(
                "SELECT payload_hash,detail FROM demo_receipts WHERE user_id=$1 AND generation=$2 AND idempotency_key=$3",
                owner,
                request.generation,
                request.idempotency_key,
            )
            if prior:
                if prior["payload_hash"] != digest:
                    raise DemoError(
                        409, "Idempotency key was already used with another order."
                    )
                return Receipt.model_validate_json(prior["detail"])
            if case["submissions"] >= DEMO_MAX_SUBMISSIONS:
                raise DemoError(
                    429,
                    "Session submission limit reached. History remains available until expiry.",
                )
            before = await self._values(conn, owner)
            accounts, positions = (
                AsyncpgAccountsRepository(conn),
                AsyncpgPositionsRepository(conn),
            )
            account = await accounts.get_account(owner)
            assert account is not None
            position = await positions.get_position(owner, "EQ-ACME")
            now = datetime.now(timezone.utc)
            domain_order = request.to_domain_request(owner)
            fixture = CASES[case["case_id"]]
            order_id, reason, status = None, None, None
            fills, filled, consideration, average = [], 0, 0.0, None
            residual, disposition = request.quantity, "rejected"
            try:
                plan = prepare_execution(
                    domain_order, fixture.book, account, position, now, self.engine
                )
            except (InsufficientBalanceError, InsufficientPositionError) as exc:
                reason = str(exc)
            else:
                fills = [FillDetail(**asdict(fill)) for fill in plan.fills]
                filled = sum(fill.quantity for fill in plan.fills)
                residual, consideration = plan.residual, plan.consideration
                average = consideration / filled if filled else None
                disposition = (
                    "filled"
                    if not residual
                    else "partially_filled_final"
                    if filled
                    else "not_filled_final"
                )
                status, order_id = plan.status.value, uuid4().hex
                await accounts.upsert_account(plan.account)
                if filled and plan.position is not None:
                    await positions.upsert_position(plan.position)
                await AsyncpgOrdersRepository(conn).create_order(
                    OrderRecord(
                        order_id=order_id,
                        user_id=owner,
                        instrument_id="EQ-ACME",
                        side=domain_order.side,
                        order_type=domain_order.order_type,
                        quantity=request.quantity,
                        filled_quantity=filled,
                        limit_price=request.limit_price,
                        average_price=average,
                        status=plan.status,
                        time_in_force="GTC",
                        created_at=now,
                        updated_at=now,
                    )
                )
            receipt = Receipt(
                receipt_id=uuid4(),
                order_id=order_id,
                generation=request.generation,
                case_id=case["case_id"],
                snapshot_id=request.snapshot_id,
                fixture_version=FIXTURE_VERSION,
                submitted=request,
                disposition=disposition,
                legacy_status=status,
                reason=reason,
                fills=fills,
                filled_quantity=filled,
                residual_quantity=residual,
                consideration=consideration,
                average_fill_price=average,
                before=before,
                after=await self._values(conn, owner),
                book=fixture.book.model_dump(mode="json"),
                recorded_at=now,
                conventions=CONVENTIONS,
            )
            await conn.execute(
                "INSERT INTO demo_receipts(receipt_id,user_id,generation,idempotency_key,payload_hash,order_id,detail) VALUES($1,$2,$3,$4,$5,$6,$7::jsonb)",
                receipt.receipt_id,
                owner,
                request.generation,
                request.idempotency_key,
                digest,
                order_id,
                receipt.model_dump_json(),
            )
            await conn.execute(
                "UPDATE demo_cases SET submissions=submissions+1 WHERE user_id=$1",
                owner,
            )
        # Transaction context exited (commit succeeded) before a success response.
        return receipt

    async def history(self, owner: str, limit: int, offset: int) -> dict[str, object]:
        async with self.pool.acquire() as conn, conn.transaction():
            case = await self._lock(conn, owner)
            rows = await conn.fetch(
                "SELECT detail FROM demo_receipts WHERE user_id=$1 AND generation=$2 ORDER BY created_at DESC,receipt_id DESC LIMIT $3 OFFSET $4",
                owner,
                case["generation"],
                limit,
                offset,
            )
            return dict(
                generation=str(case["generation"]),
                receipts=[json.loads(r["detail"]) for r in rows],
                offset=offset,
                limit=limit,
                archived_note="Earlier generations are archived; owned receipt links remain readable until session expiry.",
            )

    async def receipt(self, owner: str, receipt_id: UUID) -> Receipt:
        async with self.pool.acquire() as conn, conn.transaction():
            await self._lock(conn, owner)
            detail = await conn.fetchval(
                "SELECT detail FROM demo_receipts WHERE receipt_id=$1 AND user_id=$2",
                receipt_id,
                owner,
            )
            if detail is None:
                raise DemoError(404, "Receipt not found")
            return Receipt.model_validate_json(detail)
