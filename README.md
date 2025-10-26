# Trading Board – Market Data Agent

This repository implements the market data agent for the multi‑agent trading
simulation stack. It generates synthetic prices, order books, and dealer quotes,
publishes them to Redis streams, and persists canonical state in Postgres.

## Local development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pytest
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

With the compose stack running locally:

```bash
export MARKET_DATA_SMOKE=1
pytest -k smoke
```

You can override connection strings via `MARKET_DATA_REDIS_URL`,
`MARKET_DATA_POSTGRES_DSN`, and stream names via the `MARKET_DATA_*_STREAM`
environment variables.

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
  section must contain at least one non-empty line and at least 12 words overall.
* **post-commit** – prints a short summary of the most recent commit and
  reminds you to push.

## Continuous integration / delivery

GitHub Actions workflows reside in `.github/workflows/`:

* **ci.yml** – runs on pushes and pull requests. It checks out the repo,
  installs dependencies, and executes the full pytest suite.
* **cd.yml** – runs on pushes to `main`. In addition to the CI steps, it builds
  the Docker image to ensure the container artefact is healthy.

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
