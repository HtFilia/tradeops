# Implemented simulation boundaries

```text
seeded synthetic market data → Redis streams + PostgreSQL
                                   ↓
React REST polling → auth/session → trading service → orders/cash/positions
                                           └──────→ execution stream
```

The market data, auth and trading services run with Redis and PostgreSQL in
`docker-compose.yml`. React runs separately through Vite. There is no real feed,
exchange connection or real-money execution. Portfolio/risk and the WebSocket
gateway are planned architecture in AGENTS.md, not delivered services.

## One review path

1. Start `docker compose up --build market_data trading_agent auth_service`.
2. Run `npm ci && npm run dev` in `frontend/` and open localhost:5173.
3. Sign in to the seeded demo account, submit a one-unit equity order against a
   current synthetic book, and inspect the returned order. PostgreSQL stores orders,
   account balances and positions. Feed instruments come from current configuration.
4. Review `tests/e2e/test_full_stack.py` for order persistence after repeated schema
   preparation, and `tests/trading/test_order_service.py` for normal simulated
   fills and account updates. Run the README e2e command with the local stack.

## Failure limits

`trading/services/order_service.py` publishes executions inside the unit of work.
`trading/infrastructure/uow.py` commits on exit, after that publication. A database
failure can therefore leave a published execution without a committed account
change. A post-commit publish would still have a crash/loss window. There is no
outbox, reconciliation protocol or exactly-once guarantee.

Account state is selected and later upserted without account-level serialization.
Concurrent orders can read the same balance and overwrite each other's updates.
These are static code-path risks, not reproduced production incidents. Normal
scenario tests do not establish concurrency or crash consistency.

## Automation

CI runs Python tests, frontend build and compose smoke/e2e scenarios. CD runs only
on release branches or dispatch, requires an exact version tag, and builds Docker;
registry publication is conditional on credentials. This documentation change
introduces no runtime hardening. See `.github/workflows/` for the actual policy.
