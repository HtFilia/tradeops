CREATE TABLE IF NOT EXISTS public.market_ticks (
    id SERIAL PRIMARY KEY,
    instrument_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    bid DOUBLE PRECISION NOT NULL,
    ask DOUBLE PRECISION NOT NULL,
    mid DOUBLE PRECISION NOT NULL,
    dealer_id TEXT NULL,
    metadata JSONB NULL
);

CREATE INDEX IF NOT EXISTS idx_market_ticks_instrument_ts
    ON public.market_ticks (instrument_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS public.order_books (
    id SERIAL PRIMARY KEY,
    instrument_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    levels JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_order_books_instrument_ts
    ON public.order_books (instrument_id, timestamp DESC);
