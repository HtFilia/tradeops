# AGENTS.md

Guidance for contributors and coding agents working in this repository. It separates what the code
does today from what is planned, then sets the rules every change follows.

## What exists today

TradeOps is a local trading simulation with synthetic data and no real-money execution. Three
Python services run with Redis and PostgreSQL in `docker-compose.yml`, and a React app runs through
Vite.

- **Market data** (`market_data/`): seeded geometric Brownian motion feeds for equity, option and
  future instruments, and a mean-reverting rate feed. Feeds come from configuration
  (`MARKET_DATA_INSTRUMENTS`), with scenario presets (drift shift, volatility scaling, halts,
  liquidity regime), synthetic order books and dealer quotes, and futures/swap metadata. Ticks,
  books and quotes are published to Redis streams (`marketdata_ticks`, `marketdata_order_books`,
  `marketdata_dealer_quotes` by default) and persisted to PostgreSQL. Events carry a
  `schema_version`. `market_data/management_api.py` serves `GET /health` and `GET /metrics`.
- **Trading** (`trading/`): authenticated market and limit orders on the synthetic equity
  `EQ-ACME`, filled against the latest simulated book by `trading/domain/matching.py`. Cash,
  positions and orders are persisted in PostgreSQL and executions are published to
  `execution_stream`. The rate and index-future feeds are quote-only
  (`trading/domain/capabilities.py`). An unfilled remainder does not rest in the book, orders cannot
  be cancelled, and dealer quotes cannot be traded.
- **Auth** (`auth/`): registration, login, logout and session lookup with Argon2 password hashing,
  PostgreSQL accounts and Redis-backed sessions in HTTP-only cookies. New accounts receive
  `AUTH_STARTING_BALANCE`, and startup seeds a demo account (`demo@example.com`).
- **Isolated demo** (`trading/api/demo.py`, `auth/demo.py`): guest-owned synthetic accounts with
  scoped PostgreSQL locking, durable receipts and idempotent retries; see `docs/DEMO.md`.
- **Frontend** (`frontend/`): React and Vite. It polls the REST APIs (`src/hooks/usePolling.ts`);
  there is no WebSocket.

Known limits are in `docs/ARCHITECTURE.md`: on the legacy order route, executions are published
before the database commit, and concurrent orders on one account can overwrite each other's
balance updates. There is no outbox or exactly-once delivery.

## Planned, not implemented

- A portfolio and risk service: NAV, realized and unrealized P&L, delta, DV01 and exposure
  snapshots.
- A gateway with WebSocket streams for market data, portfolio and order status.
- Resting limit orders that other users can cross, order cancellation, trading on dealer quotes,
  and bond or futures execution.

Do not describe any of these as available in code comments, documentation or commit messages until
it ships with tests.

## Tooling

- `make install` points Git at `.githooks/`, creates `./venv` and installs `requirements.txt`.
  Other targets: `test` (`pytest -m "not e2e"`), `lint` (flake8 on `market_data` and `tests`),
  `docker-up`, `docker-down`, `trading-agent-up`, `stack-up` and `smoke`.
- Hooks: `pre-commit` runs `pytest -m "not e2e"` and, when npm is available, the frontend build
  (`SKIP_TEST_COMMIT=1` skips them); `commit-msg` requires `verb: title` with one of add, remove,
  refactor, change, revert, admin or fix, a blank line, at least 12 words of detail and lines of at
  most 80 characters; `post-commit` prints a summary.
- CI (`.github/workflows/ci.yml`): unit and integration tests with the frontend build, the demo
  transaction tests, a Docker Compose smoke job, an end-to-end job (`RUN_E2E_TESTS=1`) and, on
  release branches, release-tag validation. CD (`cd.yml`) runs on `release` and `release/**` or by
  dispatch and builds the Docker image, publishing it only when registry credentials exist.

## Rules for changes

1. Keep domain logic in plain Python (`trading/domain/`, `trading/services/`, `auth/service.py`);
   FastAPI routes parse input, call a service and return its result.
2. Services communicate through Redis streams and PostgreSQL state, never through each other's
   in-memory objects.
3. Backend I/O is async. Move CPU-heavy work out of request handlers.
4. Validate every message that crosses a process boundary with a Pydantic model, and add a contract
   test when such a model changes.
5. The server decides prices, balances and quantities; the frontend only presents them.
6. Type-hint every Python function.
7. Log through `common/logging.py`, matching `logging.schema.json`; the frontend uses
   `frontend/src/lib/logging.ts` with the same fields.
8. Keep simulations reproducible: tests use fixed seeds.
9. Any change to cash, positions or P&L comes with a test, and the state change is persisted in one
   transaction.

## Tests

Write the test first, watch it fail, then implement. Markers in `pytest.ini`:

- `unit`: no network, Redis or PostgreSQL.
- `integration`: several layers together, with test databases or stubs.
- `e2e`: the full Docker Compose stack; skipped unless `RUN_E2E_TESTS=1`.

Prefer seeded data, and wait on explicit events rather than sleeps. CI must run every suite
headlessly.
