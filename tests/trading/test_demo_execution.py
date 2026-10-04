from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from trading.domain.demo import CASES, DemoOrderInput
from trading.domain.execution import prepare_execution
from trading.domain.matching import MatchingEngine
from trading.domain.models import AccountSnapshot


def test_hand_checked_full_fill_and_account_math():
    now = datetime.now(timezone.utc)
    request = DemoOrderInput(
        generation=uuid4(),
        snapshot_id="snapshot",
        idempotency_key=uuid4(),
        side="BUY",
        quantity=5,
        order_type="MARKET",
    )
    account = AccountSnapshot(
        user_id="guest",
        cash_balance=10000,
        base_currency="USD",
        margin_allowed=False,
        updated_at=now,
    )
    plan = prepare_execution(
        request.to_domain_request("guest"),
        CASES["full"].book,
        account,
        None,
        now,
        MatchingEngine(),
    )
    assert [(f.price, f.quantity) for f in plan.fills] == [(100, 3), (100.1, 2)]
    assert plan.account.cash_balance == pytest.approx(9499.8, abs=1e-8)
    assert plan.position.quantity == 5
    assert plan.position.average_price == pytest.approx(100.04, abs=1e-8)
    assert plan.residual == 0


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, 0])
def test_demo_limit_is_finite_positive(bad):
    with pytest.raises(ValidationError):
        DemoOrderInput(
            generation=uuid4(),
            snapshot_id="snapshot",
            idempotency_key=uuid4(),
            side="BUY",
            quantity=5,
            order_type="LIMIT",
            limit_price=bad,
        )
