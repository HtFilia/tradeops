# AGENTS.md

## Purpose

This document defines:

1. The core services (“agents”) in the trading simulator platform.
2. The features we are building.
3. How those agents talk to each other.
4. Coding standards and expectations (Python backend, React frontend).
5. The testing strategy: how we use Test-Driven Development (TDD) to ship safely.

This doc is the contract for contributors. If you add a feature, your PR should reflect the rules below.

---

## High-Level System Overview

We are building a multi-asset trading simulation platform with:

* **Market data simulation** (equities, equity derivatives, fixed income)
* **Order book + OTC quotes**
* **Trading / execution**
* **Portfolio valuation and P&L**
* **Risk analytics (Delta, DV01, exposure, etc.)**
* **User accounts, balances, and session auth**
* **Persistent state so a user can log out and resume later**

The platform imitates a simplified buy-side trading + risk stack in real time.

### Core goals

* Users get a starting balance.
* Prices stream live (1s or faster for liquid instruments).
* Users trade against synthetic liquidity.
* We track positions, NAV, P&L, greeks, DV01, etc.
* The whole simulation is reproducible and persisted to Postgres.

### Non-goals (for now)

* Regulatory accuracy (MiFID, best-ex rules, etc.).
* Production-grade latency (we are not trying to beat nanoseconds).
* Real money.

---

## Services / Agents

We split responsibilities into agents. Each agent is either its own process / module or a clearly separated package in the backend codebase. The messaging between them is event-driven (pub/sub, e.g. Redis Streams), not blocking RPC where possible.

This prevents one slow component (like risk calcs) from stalling the rest (like market data).

### 1. Market Data Agent

**Role:** Generate, stream, and persist synthetic market data.

**Responsibilities:**

* Simulate price paths for:

  * Equities
  * Equity derivatives (e.g. vanilla options, index futures)
  * Fixed income (e.g. government bonds, swaps)
* Generate ticks at realistic frequencies:

  * Highly liquid assets: multiple updates per second (e.g. 5 Hz)
  * Medium liquidity: ~1 Hz
  * Illiquid OTC quotes: every few seconds
  * Rule: baseline >= 1s, but bursts faster than 1s are allowed and must be handled downstream.
* Maintain and publish synthetic order books (L2 depth) for listed instruments.
* Maintain and publish multiple dealer quotes for OTC-style instruments (e.g. “Dealer A bid/ask,” “Dealer B bid/ask”).
* Write all ticks and quotes to Postgres for later replay / analytics.
* Publish live ticks and book updates onto a pub/sub channel (`marketdata_stream`).

**Current implementation status**

* Seeded GBM and mean-reverting simulators drive equities, options, and rates with configurable cadences.
* Instrument configuration builder maps YAML/JSON-style configs into `InstrumentFeed` objects (tick scheduling, per-feed metadata, optional order books & dealer quotes).
* Market data service pumps ticks, publishes to Redis streams, and persists ticks/order books/dealer quotes into Postgres repositories.
* Redis publishers encode tick/order-book/quote payloads with deterministic serialization and are exercised by integration tests.
* Runner loop exists for CLI/daemon execution, and the test suite covers simulators, configuration wiring, persistence, publishers, and service orchestration.
* Scenario controls (volatility scaling, drift shifts, halts, liquidity overrides) and additional instrument types (futures, swaps) are supported via env-supplied configs.
* Metadata factories deliver enriched payloads (swap DV01 buckets, futures contract info) and schema versioning ensures downstream compatibility guarantees.
* Operational FastAPI endpoints (`/health`, `/metrics`) surface real-time diagnostics for instrumentation and monitoring.

**Dev tooling & automation**

* Custom git hooks live in `.githooks`. Enable them via `git config core.hooksPath .githooks`.
  * `pre-commit` runs `pytest` unless `SKIP_TEST_COMMIT=1` is set.
  * `commit-msg` enforces `verb: title` + blank separator + thorough explanation (verbs: add/remove/refactor/change/revert/admin, max 80 chars per line, >=12 body words).
  * `post-commit` prints a summary and reminders after each commit.
* `Makefile` workflow:
  * `make install` configures git hooks, bootstraps `./venv`, and installs dependencies (preferred first step after cloning).
  * `make test`, `make docker-up`, `make docker-down`, and other targets wrap common routines.
  * `make smoke` invokes `scripts/run_smoke.sh` to run the docker-compose powered smoke suite locally.
* GitHub Actions:
  * `ci.yml` executes the pytest suite on pushes/PRs and runs the docker-compose smoke tests via `scripts/run_smoke.sh`.
  * `cd.yml` (pushes to `main`) repeats CI steps and performs a Docker build to validate the container image.

**Local docker stack**

* The repo ships with `docker-compose.yml`, a `Dockerfile`, and `docker/init/01_market_data.sql`. Run `docker compose up --build market_data` to start Redis, Postgres, and the market data agent together.
* Redis: `docker compose exec redis redis-cli monitor` lets you inspect the published streams (`marketdata_ticks`, `marketdata_order_books`, `marketdata_dealer_quotes`). Update stream names via env vars in the compose file.
* Postgres: `docker compose exec postgres psql -U postgres -d marketdata` opens a shell. Tables `market_ticks` and `order_books` are initialised automatically; adjust schema via new SQL in `docker/init`.
* Agent configuration is controlled by environment variables (connection strings, stream names, default intervals) and optional JSON payload `MARKET_DATA_INSTRUMENTS`. Edit the compose service `environment` block or supply an `.env` file when you need custom feeds.
* Adding another microservice to the stack: either extend `docker-compose.yml` with a new service definition (reuse the `market_data` service pattern) or supply an override file in your feature branch. Keep build contexts rooted at the repo and prefer passing configuration through environment variables rather than modifying the base image.
* Smoke tests exist in `tests/test_smoke_stack.py`. Run `make smoke` (or `scripts/run_smoke.sh`) to build the stack, execute the suite, and tear everything down. Set `MARKET_DATA_SMOKE=1` and point `MARKET_DATA_REDIS_URL`, `MARKET_DATA_POSTGRES_DSN`, and related stream env vars at your running compose stack before executing `pytest -k smoke` manually. Tests will skip automatically when the stack is unavailable.

**Next steps**

1. Automate compose-based smoke tests in CI (spinning stack, running the new integration spec).
2. Expand the configuration schema with richer metadata factories (curve buckets, contract calendars) and persist scenario definitions for reproducibility.
3. Add stress/regime controls (volatility regimes, trading halts) and scenario fixtures for integration tests and demos.
4. Expose a FastAPI management endpoint to monitor feed health and surface runtime metrics (last tick per instrument, publish latencies).

**Why this agent is isolated:**

* Market data is the heartbeat of everything else. It must keep going, even if trading or risk is doing something heavy.
* This mirrors how real trading infra isolates “market data handlers.”

---

### 2. Trading Agent

**Role:** Accept orders from users and generate fills.

**Responsibilities:**

* Accept new orders (market, limit).
* For listed products:

  * Match user orders against the current simulated order book.
  * Add user limit orders into that book so users can cross each other (peer-style liquidity).
* For OTC products:

  * Allow a user to “hit”/“lift” a specific dealer quote.
* Generate trade executions/fills.
* Update user cash balances and open positions in Postgres (atomic transaction).
* Publish executions/fills onto `execution_stream`.

**Why isolated:**

* Trading logic has to enforce rules (no negative balance unless margin allowed, etc.).
* It’s the gatekeeper of account mutation. That logic must stay auditable and testable.

**Implementation notes:**

* Domain contracts and simulators live under `trading/domain/`.
* Service coordination, matching, and validation reside in `trading/services/order_service.py`.
* FastAPI and infrastructure wiring are exposed via `trading/app.py` with adapters in `trading/infrastructure/`.
* End-to-end, domain, and contract tests execute from `tests/trading/`.

---

### 3. Portfolio & Risk Agent

**Role:** Mark every user’s book in real time, compute risk, and stream it to the UI.

**Responsibilities:**

* Listen to:

  * `execution_stream` (position changes, cash changes)
  * `marketdata_stream` (mark-to-market price changes)
* Maintain current portfolio state per user:

  * Cash
  * Positions by instrument
  * Average cost per instrument
  * Realized P&L and Unrealized P&L
  * Total NAV
* Compute buy-side style risk metrics:

  * **Delta exposure** by underlying
  * **DV01 / IR01** for rates/bonds
  * Exposure by asset class
  * Leverage / concentration metrics
* Publish a “portfolio snapshot” per user to `risk_stream` for UI consumption.
* Persist periodic snapshots in Postgres for historical P&L charts.

**Why isolated:**

* Risk math may get heavy later (curves, Greeks, stress tests, Monte Carlo VaR, ML strategies).
* We also plan to do ML here eventually. Python is the backend language, so this agent is where quant-y stuff will live.

---

### 4. Auth & User Management Agent

**Role:** Handle identity, security, and entitlements.

**Responsibilities:**

* Secure account creation (password hashing with Argon2/bcrypt).
* Session management (HTTP-only secure cookies with server-side session storage in Redis).
* Assign initial starting balance when a user registers.
* Enforce access:

  * You can only see your own portfolio.
  * You can only trade if you’re authenticated.
  * You cannot modify other users’ orders.

**Why isolated:**

* Security code must stay clean and reviewable.
* Keeps secrets and auth logic out of market/risk code.

**Current implementation status**

* Package now lives under `auth/` (renamed from the earlier `auth_agent/` scaffold for clarity).
* Domain services (`auth/service.py`) coordinate registration, login, and logout with Argon2 hashing, account provisioning, and session issuance.
* HTTP surface (`auth/app.py`) exposes `/auth/register`, `/auth/login`, and `/auth/logout` using FastAPI, issuing/removing secure cookies.
* Persistence and session abstractions are defined for Postgres and Redis integration (`auth/storage.py`, `auth/session.py`).
* Unit and API-level tests cover the happy path and guardrails (`tests/test_auth_service.py`, `tests/test_auth_api.py`) with reusable stubs in `tests/auth_stubs.py`.

**Next steps**

1. Wire the repositories to real asyncpg and Redis clients (current tests rely on in-memory stubs).
2. Add database migrations for the `users` and `accounts` tables plus seed scripts for local environments.
3. Extend functional tests to exercise cookie/session handling against a live Redis container (compose or test harness).
4. Expose additional endpoints for password reset and session introspection once core flows are stable.
5. Integrate auth agent deployment into the docker-compose stack and CI smoke tests alongside market data.

---

### 5. API Gateway / WebSocket Gateway Agent

**Role:** Public-facing interface for the frontend.

**Responsibilities:**

* REST endpoints:

  * /auth (login/logout, register)
  * /instruments (static metadata)
  * /orders (place, cancel)
  * /history (ticks, candles, trades)
  * /portfolio (snapshots, P&L history)
* WebSocket endpoints:

  * Live market stream (subset of instruments user is watching)
  * Live portfolio/risk stream (that specific user only)
  * Live order status updates
* Fan-out events from `marketdata_stream`, `execution_stream`, and `risk_stream` to the browser.

**Why isolated:**

* We want to firewall the internal event bus from the public internet.
* It also gives us a single point to enforce rate limiting / throttling later.

---

## Tech Stack

### Backend

* **Language:** Python

  * Reason: we will integrate ML for pricing / risk / strategies later.
  * Risk, curves, Greeks, scenario analysis… Python is the industry standard for that.
* **Framework style:**

  * FastAPI (or similar async Python framework)
  * Async IO everywhere (to handle bursts of sub-second ticks from liquid symbols).
* **Inter-service communication:**

  * Redis Streams or pub/sub channels

    * Low latency
    * Replay support for recent messages
    * Simpler than Kafka to develop locally
* **Database:**

  * Postgres

    * ACID for trades and balances
    * Time-series-ish tables for ticks
  * TimeScaleDB extension is allowed later, but not required for v0
* **Caching / hot state:**

  * Redis for:

    * last known best bid/ask per instrument
    * user session state
    * most recent portfolio snapshot per user

### Frontend

* React SPA
* WebSocket client for live updates
* Dark mode by default (this is a trading app, not a hospital UI)
* Current minimal UI lives under `frontend/` (React + Vite) and polls REST
  endpoints until the WebSocket gateway is ready.

---

## Data Model (Very High Level)

We will maintain at least:

* `users`

  * id
  * email
  * password_hash
  * created_at

* `accounts`

  * user_id
  * cash_balance
  * base_currency
  * margin_allowed (bool)

* `instruments`

  * instrument_id
  * type (EQUITY / OPTION / FUTURE / BOND / SWAP / ETC)
  * tick_size
  * lot_size
  * currency
  * maturity (nullable)
  * underlier_instrument_id (nullable)

* `market_ticks`

  * instrument_id
  * timestamp
  * bid
  * ask
  * mid
  * dealer_id (nullable for OTC, null for listed)
  * metadata (JSONB: vol, spread, liquidity regime, etc.)

* `order_books`

  * instrument_id
  * timestamp
  * levels (JSONB snapshot of top-of-book depth)

* `orders`

  * order_id
  * user_id
  * instrument_id
  * side (BUY/SELL)
  * qty
  * limit_price (nullable for market)
  * status (OPEN / PARTIAL / FILLED / CANCELLED)
  * time_in_force
  * created_at
  * updated_at

* `trades`

  * trade_id
  * order_id
  * user_id
  * instrument_id
  * qty_filled
  * price
  * timestamp

* `positions`

  * user_id
  * instrument_id
  * qty
  * avg_cost

* `portfolio_snapshots`

  * user_id
  * timestamp
  * nav
  * cash_balance
  * unrealized_pnl
  * realized_pnl
  * delta_exposure (JSONB)
  * dv01_exposure (JSONB)

We keep JSONB for multi-bucket exposures (per-underlier delta, curve DV01 buckets, etc.) without schema churn every time we add a new risk dimension.

---

## Coding Standards / Best Practices

### 1. Modularity / Agent boundaries

* Each agent should be able to run independently.
* Never let one agent reach directly into another agent’s private in-memory structures.
* Communication happens through:

  * Redis Streams events
  * Postgres state
  * (For read access only) Redis caches

Why?
We want to be able to kill/restart Risk without crashing Market Data. That mirrors real desks: market data and PnL calc are decoupled.

### 2. Async first

* All I/O in backend Python must be async.

  * Market data → bursts under 1s.
  * User can place an order while 10 symbols are ticking.
  * We cannot afford naive blocking code.
* Use `async`/`await` in FastAPI routes, Redis clients, and DB access.
* Any CPU-heavy calc (e.g. Greek surfaces later) should be pushed to a worker pool or a separate process.

### 3. Determinism and reproducibility

* The Market Data Agent must be able to:

  * run in “live mode” (random walk + noise)
  * run in “seeded mode” (fixed RNG seed for deterministic replay)
* This is critical for tests, demos, and debugging.

### 4. No direct trust of client input

* Server, not client, decides:

  * executable price
  * whether you actually have enough balance
  * whether quantity is valid (lot size)
* The frontend is presentation, NOT authority.

### 5. Thin controllers, fat domain logic

* Don’t bury real logic in FastAPI route handlers.
* Route handler should parse input, call a domain service, return output.
* Domain services (pure Python classes/functions) should be:

  * unit testable in isolation
  * not tied to HTTP / Redis / DB

This is how we keep testing clean.

### 6. Type hints everywhere

* All Python functions are fully type hinted.
* We will treat missing type hints as a bug.
* Why? Consistency + future static analysis + possible mypy/marshmallow/pydantic validation.

### 7. Structured logging contract

* All services (backend and frontend) emit JSON logs that match `logging.schema.json`.
* Use `common/logging.py` in Python agents to configure loggers; frontend code should
  mirror the same field names when instrumentation lands.
* Every log should include a human-readable `message`, a machine-friendly `event`
  key, and attach any additional details inside the `context` object to keep the
  schema stable for downstream ingestion.

### 8. Pydantic models for IO schemas

* Any data crossing process boundaries (e.g. a Tick on `marketdata_stream`, an Execution on `execution_stream`) MUST be defined as a Pydantic model.
* This gives:

  * Validation
  * Versioning
  * Self-documenting contracts between agents and frontend

---

## TDD: Test Driven Development

We practice strict TDD:

1. Write tests that describe the behavior you want.
2. Watch them fail.
3. Implement the behavior.
4. Refactor only after tests are passing.

Why we’re doing this:

* We have multiple agents talking asynchronously. This kind of system rots FAST without tests.
* We will build risk models and (eventually) ML. We need confidence we’re not silently corrupting NAV.

### Types of tests we require

#### 1. Unit Tests

Granular, fast, pure-Python.

* Example targets:

  * Price path generator (GBM for equities, mean-reverting rates for bonds)
  * Order book update logic
  * Matching engine: given an order book, does a BUY 100 @ 100.05 fill correctly?
  * P&L calc: given fills + marks → unrealized and realized P&L
  * DV01 calc: given bond cashflows and current yield → price sensitivity per bp

Rules:

* Unit tests MUST NOT touch network, Redis, Postgres.
* They operate on pure functions / objects.

We want extremely high coverage here.

---

#### 2. Integration Tests

These test “agent-level correctness.”

Examples:

* Trading Agent integration test:

  * Spin up an in-memory Postgres test DB.
  * Seed: user has $1,000,000 cash.
  * Send a mock limit BUY order.
  * Inject a mock order book tick where ask <= limit.
  * Assert:

    * Order becomes FILLED.
    * Cash decreases appropriately.
    * Position increases.
    * A `trade` record was created.
    * A message was written to `execution_stream`.

* Portfolio & Risk Agent integration test:

  * Seed: user long 100 AAPL @ $100.
  * Send fake marketdata_stream tick: AAPL mid = $105.
  * Assert:

    * Unrealized PnL = (105 - 100) * 100.
    * NAV updated.
    * Published snapshot includes correct delta.

Rules:

* Integration tests can use:

  * A test Postgres schema
  * A local Redis test instance or mock Redis
  * The agent's real service code paths

These tests ensure “does the agent behave in a realistic end-to-end way?”

---

#### 3. Contract / Schema Tests

These tests guarantee messages don’t silently drift.

We will have Pydantic models like `TickEvent`, `ExecutionEvent`, `PortfolioSnapshot`.

Contract tests should verify:

* Serializing and deserializing these models works and is backward-compatible.
* Required fields are present.
* Types are respected (e.g. instrument_id is a string UUID, timestamp is ISO 8601, etc.).
* Forbidden fields aren’t leaking (e.g. never expose another user’s PnL in my snapshot).

This matters because the WebSocket Gateway and frontend rely on these exact schemas.

---

#### 4. API / Endpoint Tests

These tests hit FastAPI endpoints.

Examples:

* `POST /auth/register`:

  * Returns 201
  * Creates a user row with hashed password
  * Creates an account row with default starting balance
  * Sets secure session cookie

* `POST /orders` (authenticated):

  * Rejects order if not logged in
  * Rejects qty=0
  * Rejects if notional > cash and margin not allowed
  * Accepts a valid order and returns order_id

These tests make sure that the public interface is sane and we’re not introducing security regressions.

---

#### 5. Scenario / Simulation Tests (full system sanity)

These are slower “story tests” that simulate actual usage.

Example scenario:

1. User registers (gets $1,000,000).
2. Market Data Agent publishes ticks for a bond and an equity.
3. User buys both.
4. Trading Agent fills.
5. Portfolio & Risk Agent recomputes NAV.
6. User hits `/portfolio` and sees updated NAV, positions, and DV01.

We assert:

* NAV matches cash + MTM of positions.
* DV01 makes sense (bond contributes, equity doesn’t).
* Delta exposure matches quantities.

These tests prove the entire pipeline works “front-to-back” and are the closest thing to regression tests for big refactors.

We treat these as `e2e` tests in the repo. They are skipped by default and only
run when `RUN_E2E_TESTS=1` is present (CI or a developer with the stack running).

---

### TDD Rules / Process

* You do not commit new functionality without at least:

  * Unit tests for local logic
  * One integration or endpoint test showing that logic from the user’s point of view
* If you’re changing a Pydantic model that goes over WebSocket, you add/adjust a contract test.

When writing tests:

* Prefer deterministic seeded data.
* Avoid sleeps/timeouts for async: instead, await explicit events or inject pre-baked messages.
* CI must be able to run the full test suite headlessly.

---

## Roadmap / Initial Milestones

**Milestone 1: Auth & Accounts**

* Register / Login / Session cookie
* Create account with starting balance
* Postgres schema migration
* Unit + API tests

**Milestone 2: Market Data Agent (MVP)**

* Instrument master table
* Deterministic price simulator for:

  * 1 equity
  * 1 bond
* Publish ticks to Redis
* Persist ticks to Postgres
* Unit tests for simulator math
* Integration test for tick publish + persist

**Milestone 3: Trading Agent (MVP)**

* Place market buy/sell on that equity
* Match against a basic synthetic book
* Update cash, positions
* Write trade records
* Publish execution event
* Integration test: place→fill→positions updated

**Milestone 4: Portfolio & Risk Agent (MVP)**

* Subscribe to ticks + executions
* Compute NAV, P&L, delta
* Persist portfolio snapshot
* Expose `/portfolio` via API Gateway
* Integration test: verify NAV math across a fill

**Milestone 5: Frontend (MVP)**

* Login screen
* Market watch (live price via WebSocket)
* Simple order ticket (buy/sell)
* Portfolio dashboard (cash, NAV, P&L)

After that:

* Add DV01
* Add multi-dealer OTC quotes
* Add multi-level order books
* Add stress scenarios (“what if rates +100bps?”)
* Add machine learning alpha / pricing / anomaly detection in the Risk Agent

---

## Final notes

* Each agent must treat external messages as untrusted input. Validate with Pydantic before acting.
* Never assume 1-second cadence. The system must tolerate multiple ticks arriving <1s apart for different instruments.
* All state changes that affect money (cash, positions, P&L) must be persisted in Postgres in a single transaction or rolled back. No partial commits.
* If state changes user PnL, there must be a test for it.
