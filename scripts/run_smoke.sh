#!/usr/bin/env bash
set -euo pipefail

echo "[smoke] Starting docker compose stack..."
docker compose up -d --build market_data

cleanup() {
  echo "[smoke] Tearing down docker compose stack..."
  docker compose down
}

trap cleanup EXIT

export MARKET_DATA_SMOKE=${MARKET_DATA_SMOKE:-1}
export MARKET_DATA_REDIS_URL=${MARKET_DATA_REDIS_URL:-redis://localhost:6379/0}
export MARKET_DATA_POSTGRES_DSN=${MARKET_DATA_POSTGRES_DSN:-postgresql://postgres:postgres@localhost:5432/marketdata}

echo "[smoke] Running pytest smoke suite..."
pytest -k smoke
