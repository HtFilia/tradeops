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

* **pre-commit** – runs `pytest` to guard regressions. Set
  `SKIP_TEST_COMMIT=1 git commit ...` to bypass in emergencies (the hook warns
  when tests are skipped).
* **commit-msg** – enforces the standard commit message format:
  ```
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

```
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

## Structured Logging

All services emit JSON logs that follow `logging.schema.json`. The helper in
`common/logging.py` wires Python's logging subsystem to this schema, ensuring
messages stay human-readable while remaining easy to ingest elsewhere. Frontend
code should serialize the same field set (`timestamp`, `level`, `component`,
`event`, `message`, optional correlation identifiers, and a `context` object)
when we instrument SPA interactions.

### Running the HTTP API

```
uvicorn trading.app:create_default_app --factory --reload
```

Configuration is sourced from the same environment variables used across the
stack (`TRADING_REDIS_URL`, `TRADING_POSTGRES_DSN`, `TRADING_MARKETDATA_STREAM`,
`TRADING_EXECUTION_STREAM`, `TRADING_ORDER_STREAM`). The bootstrap wiring opens
an asyncpg pool and a Redis client on startup; ensure the services from the
docker-compose stack are available before launching the API.

### Tests

```
venv/bin/pytest tests/trading
```

The suite covers domain contracts, infrastructure adapters, service coordination,
and the FastAPI surface, keeping regression protection in line with our TDD
expectations.
