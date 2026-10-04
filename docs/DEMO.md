# Snapshot execution investigation

The primary public UI creates an isolated synthetic guest account. It shows the
selected immutable EQ-ACME book, an order preview, actual per-level fills, cash
and holdings reconciliation, and PostgreSQL-backed receipt history.

## Four fixture outcomes

All cases start with 10,000 synthetic USD and zero holdings. Prices are USD/share,
quantities integer shares. Fixture `equity-snapshots-v1` has a fixed timestamp
2024-01-02 14:30 UTC; it is not a current quote. Bids are 3 @ 99.90 and 4 @ 99.80.

| Case | Suggested action | Expected result |
|---|---|---|
| Full | Buy 5 market; asks 3 @ 100.00, 4 @ 100.10 | 5 filled; 500.20 consideration; 100.04 weighted price; 9,499.80 cash |
| Shallow | Buy 5 market; asks 2 @ 100.00, 1 @ 100.20 | 3 filled; 2 residual final; 300.20 consideration; 9,699.80 cash |
| Limit | Buy 5 limit 99.90 on full book | No fill; cash/holding unchanged; no future monitoring |
| Rejection | Sell 1 with no holdings | Rejected before matching; account unchanged; persisted rejected attempt |

Buy 5 then sell 5 on the full book costs 500.20 and returns 499.30. Final cash is
9,999.10 and holdings zero. This known spread loss is synthetic, not a financial
result. No fees, leverage, short selling, margin, portfolio valuation or risk
analytics are implemented. Futures and bond-yield feed quotes remain read-only.

## API / ownership

`POST /auth/demo/start` issues/resumes the existing HttpOnly cookie session. Guest
identity is server-chosen and never accepted from request parameters. The homelab
serves the trading routes below under its existing `/api/trading` prefix.

- `GET /demo/account`: coherent owned generation, cash, holdings and limits.
- `GET /demo/book`: immutable server-owned snapshot and suggested action.
- `POST /demo/reset`: current generation and selected case; fresh account baseline.
- `POST /demo/orders`: generation, snapshot ID, UUID idempotency key and order.
- `GET /demo/orders?limit=20&offset=0`: bounded current-generation history.
- `GET /demo/orders/{receipt_id}`: owned receipt, including archived generations.

Wrong-owner receipt requests return 404. Missing/expired sessions return 401.
Cross-origin browser mutations are rejected; mutations require JSON. Invalid
fields return 422, stale generations/changed idempotency payloads 409, resource
limits 429, and guest capacity exhaustion 503. Accepted receipts return 201;
financial rejections return 400 with a typed persisted receipt. Same-key retries
return the original outcome, including financial rejections. Invalid-schema
requests are not recorded as orders.

The payload identity is derived from the validated canonical request. Reset
makes a new generation and archives earlier receipts without deleting them.
An old generation cannot be submitted or retried. Retry guarantees last only
while the guest session/generation remains valid. Refresh reloads persisted
receipts; downloads are actual versioned JSON receipt data.

## Accounting / transaction boundary

[MatchingEngine](../trading/domain/matching.py) selects real snapshot levels.
[Shared pure execution](../trading/domain/execution.py) handles cash, weighted
buy cost and sell holdings for both legacy and guided services. Selling more
than the requested available holding is rejected in full, even if a shallow
book would fill fewer shares. Buy cash validation uses the actual available
fills; an insufficient-cash match is rejected in full.

The new [demo service](../trading/services/demo_service.py) locks case then
account in PostgreSQL. Reset and submissions serialize on that boundary. It
persists order, exact fill detail, before/after state and idempotency record in
one transaction. Returned after-state is read from stored account/positions,
including NUMERIC cash precision (4 decimals) and average-cost precision (6).
A receipt is returned only after commit. Floating-point consideration and
weighted prices use justified absolute tolerances in tests.

Each submission matches the same supplied snapshot again. It does not consume
shared exchange liquidity. Zero-fill and residual outcomes are final. Receipt
history proves PostgreSQL execution/accounting, not reliable Redis publication.
The legacy order service retains its pre-commit event publication and untested
same-account concurrency limitations; no general outbox guarantee is claimed.
Guest accounts cannot submit through the legacy unbounded order route.

## Bounds / lifecycle

Defaults are configurable via environment, validated against upper bounds:

| Setting | Default |
|---|---|
| `DEMO_TTL_MINUTES` | 120 |
| `DEMO_MAX_GUESTS` | 200 active guests |
| `DEMO_MAX_SUBMISSIONS` | 100 total attempts per session, including financial rejections |
| `DEMO_MAX_RESETS` | 20 per session |

Starts are limited to 5/minute and resets to 10/minute per server-resolved peer
using atomic Redis counters. Proxies must preserve the trusted loopback-forwarded
client address; no browser-supplied owner or arbitrary forwarded address is
trusted by application code. These defaults are resource bounds, not measured
VPS capacity. Authentication expiry can occur before database retention.

The existing homelab retention job runs the narrowly scoped guest cleanup in
[02_demo_guest_retention.sql](../deploy/02_demo_guest_retention.sql), alongside
feed pruning. It deletes at most 1,000 guest owners per run after their expiry
has been more than 24 hours, skips locked cases, and explicitly preserves
ordinary/shared accounts. Cascades remove only their owned orders/receipts.
The job tolerates an older release without guest tables. No cleanup runs during
migration. End session revokes the cookie, leaving evidence until expiry/cleanup.

## Migration / rollback

[Schema v1](../common/schema.py) is additive and idempotent. Auth and trading both
prepare it under one advisory lock before serving; startup order is immaterial.
Existing users default to `registered`. Guest password login is prohibited; the
stored hash is of an unexposed random password, so an older binary also cannot
use a predictable credential. No prior orders or columns are removed. The old
`auth.server._prepare_schema` import remains compatible.

Deployment performs schema preparation automatically. Before releasing, use the
existing homelab PostgreSQL backup service and check its dump. Rollback uses the
previous application release and leaves schema intact. An older UI cannot use
the new guided receipts; those remain in the database. A database restore is a
separate recovery action, not an automatic destructive rollback.

## Verification

`PYTHONPATH=. .venv/bin/python -m pytest -m 'not e2e'` runs fast checks. The real
transaction suite is opt-in against a dedicated `demo_test` database and test
Redis port 18579; never use a deployed database. CI has isolated PostgreSQL 17
and Redis 8 services for this suite.

```sh
DEMO_TEST_POSTGRES_DSN=postgresql://postgres:postgres@127.0.0.1:18543/demo_test \
DEMO_TEST_REDIS_URL=redis://127.0.0.1:18579/12 \
PYTHONPATH=. .venv/bin/python -m pytest tests/demo -q
```

[Tests](../tests/demo/test_owned_execution.py) cover owners, history, expiry,
revocation, origin checks, retries, simultaneous spending, reset races,
buy/sell conservation, rejected/partial/zero fills, database rollback, populated
old-schema migration and cleanup excluding ordinary accounts. The existing
legacy E2E remains separate. `frontend/tests/demo.browser.cjs` uses actual APIs,
four cases, keyboard execution, reload/history, JSON downloads, mobile and both
themes. The mocked legacy dashboard check remains in place. Run browser checks
against a temporary stack, never the shared public account.
