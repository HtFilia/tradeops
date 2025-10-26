# Trading Board – Market Data Agent

This repository implements the market data agent for the multi‑agent trading
simulation stack. It generates synthetic prices, order books, and dealer quotes,
publishes them to Redis streams, and persists canonical state in Postgres.

## Local development

```bash
make install
```

The `install` target does three things:

1. Configures git to use the repo’s custom hooks (`git config core.hooksPath .githooks`)
   and ensures they are executable.
2. Creates (or reuses) a local virtual environment in `./venv`.
3. Installs Python dependencies from `requirements.txt`.

Once installed, run tests with:

```bash
venv/bin/pytest
```

To build the docker stack and run the smoke suite locally, execute:

```bash
make smoke
```

### Docker stack

Run the entire stack (Redis, Postgres, market data agent) with Docker Compose:

```bash
docker compose up --build market_data
```

Useful commands:

* Inspect Redis stream traffic: `docker compose exec redis redis-cli monitor`
* Inspect Postgres tables: `docker compose exec postgres psql -U postgres -d marketdata`

### Smoke test (compose required)

`make smoke` compiles the docker images, launches Redis/Postgres/market data,
runs `pytest -k smoke`, and tears the stack down automatically. To execute the
smoke suite manually:

```bash
export MARKET_DATA_SMOKE=1
export MARKET_DATA_REDIS_URL=redis://localhost:6379/0
export MARKET_DATA_POSTGRES_DSN=postgresql://postgres:postgres@localhost:5432/marketdata
pytest -k smoke
```

Stream names can be customised via the `MARKET_DATA_*_STREAM` environment
variables.

## Git hooks

Custom hooks live in `.githooks`. Enable them once per clone:

```bash
git config core.hooksPath .githooks
```

Hook responsibilities:

* **pre-commit** – runs `pytest -m "not e2e"` and (when the frontend is
  present) `npm run build`. Set `SKIP_TEST_COMMIT=1 git commit ...` to bypass in
  emergencies (the hook warns when checks are skipped).
* **commit-msg** – enforces the standard commit message format:

  ```text
  verb: concise title
  
  thorough explanation covering design choices, wrapped at 80 chars
  ```

  `verb` must be one of: add/remove/refactor/change/revert/admin. The detail
  section must start after a blank line, contain at least one non-empty line,
  and total at least 12 words. Every line (subject and body) must be ≤80 chars.
* **post-commit** – prints a short summary of the most recent commit and
  reminds you to push.

## Continuous integration / delivery

GitHub Actions workflows reside in `.github/workflows/`:

* **ci.yml** – runs on pushes and pull requests. It checks out the repo,
  installs dependencies, executes the unit/integration suite, and then invokes
  `scripts/run_smoke.sh` to validate the docker-compose stack end-to-end.
* **cd.yml** – runs on pushes to `main`. In addition to the CI steps, it builds
  the Docker image to ensure the container artefact is healthy.

## Operational API

The management FastAPI application (`market_data/management_api.py`) exposes
runtime diagnostics for the agent:

* `GET /health` – last emitted tick per instrument and current liquidity regime.
* `GET /metrics` – configured tick cadence/tick size plus registered scenario
  presets.

Mount this app alongside the streaming service when you need operational
visibility or integration with external monitoring.

## Commit message template

```text
verb: title

Detailed explanation with multiple sentences explaining the change,
covering design trade-offs, and future considerations. Wrap each line at
80 characters to retain readability in terminals and tooling.
```

Allowed verbs: `add`, `remove`, `refactor`, `change`, `revert`, `admin`.

Remember to keep explanations thorough—describe the behaviour change, the reason
behind it, and notable testing decisions.

## Trading Agent

An asynchronous trading agent now lives under `trading/`. It accepts authenticated
order requests, matches them against the latest simulated order book, persists
cash/position state, and publishes executions onto the configured Redis stream.

## Frontend UI (React + Vite)

A lightweight React single-page app lives in `frontend/`. It polls the market
data management API for the latest ticks and submits demo orders to the trading
agent. Both backends expose CORS-friendly endpoints by default so the UI can run
locally via Vite.

### Getting started

1. Start the docker stack so Redis, Postgres, market data, the trading agent,
   and the auth service are running. The services expose:
   * Market data management API – `http://localhost:8080`
   * Trading agent REST API – `http://localhost:8081`
   * Auth service – `http://localhost:8082`

   ```bash
   make stack-up        # or: docker compose up --build market_data trading_agent auth_service
   ```

2. Install frontend dependencies and launch the dev server:

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

   Vite serves the UI on `http://localhost:5173` (configurable via
   `VITE_DEV_PORT`). The page displays live market snapshots and an order form.
3. To customise service endpoints, set the following environment variables
   before running the dev server:

   ```bash
   export VITE_MARKET_DATA_BASE_URL="http://localhost:8080"
   export VITE_TRADING_BASE_URL="http://localhost:8081"
   export VITE_AUTH_BASE_URL="http://localhost:8082"
   ```

4. Hit `http://localhost:5173` and use the sign-in form. Registration is wired
   through the auth agent; newly created users receive starting balances defined
   by `AUTH_STARTING_BALANCE`. A demo account (`demo@example.com` / `demo`) is
   seeded automatically for quick testing.

All UI interactions emit JSON logs that match `logging.schema.json`, keeping the
schema consistent with backend services.

## Structured Logging

All services emit JSON logs that follow `logging.schema.json`. The helper in
`common/logging.py` wires Python's logging subsystem to this schema, ensuring
messages stay human-readable while remaining easy to ingest elsewhere. Frontend
code should serialize the same field set (`timestamp`, `level`, `component`,
`event`, `message`, optional correlation identifiers, and a `context` object)
when we instrument SPA interactions.

### Running the HTTP API

```bash
uvicorn trading.app:create_default_app --factory --reload
```

Configuration is sourced from the same environment variables used across the
stack (`TRADING_REDIS_URL`, `TRADING_POSTGRES_DSN`, `TRADING_MARKETDATA_STREAM`,
`TRADING_EXECUTION_STREAM`, `TRADING_ORDER_STREAM`). The bootstrap wiring opens
an asyncpg pool and a Redis client on startup; ensure the services from the
docker-compose stack are available before launching the API.

### Tests

We organise tests by scope using Pytest markers:

* `unit` – fast, isolated tests (default marker for many modules)
* `integration` – exercises multiple layers (database/redis/service wiring)
* `e2e` – full stack verification requiring the docker compose stack

Common commands:

```bash
# Run unit + integration tests locally
venv/bin/pytest -m "not e2e"

# Run only unit tests
venv/bin/pytest -m unit

# Run integration tests
venv/bin/pytest -m integration
```

End-to-end tests are gated behind an environment flag so they only run when the
stack is available (typically CI):

```bash
RUN_E2E_TESTS=1 \
E2E_MARKET_URL=http://localhost:8080 \
E2E_TRADING_URL=http://localhost:8081 \
E2E_AUTH_URL=http://localhost:8082 \
venv/bin/pytest -m e2e
```

The frontend also ships with `npm run build` for CI verification.

## Release process

* Release work happens on the `release` branch (or `release/*` branches).
* Each release commit must be tagged with the application version in the
  `x.y.z` or `x.y.z+flag` format (for example `1.2.0` or `1.2.0+hotfix`).
  tags are enforced by CI.
* The CD workflow builds and publishes the Docker image using the release tag as
  the image version.
