import { logger } from "./logging";

const marketDataBaseUrl =
  import.meta.env.VITE_MARKET_DATA_BASE_URL ?? "http://localhost:8080";
const tradingBaseUrl = import.meta.env.VITE_TRADING_BASE_URL ?? "http://localhost:8081";
const authBaseUrl = import.meta.env.VITE_AUTH_BASE_URL ?? "http://localhost:8082";

const defaultFetchOptions: RequestInit = {
  credentials: "include",
  headers: {
    "Content-Type": "application/json"
  }
};

function buildUrl(base: string, path: string): string {
  return `${base.replace(/\/+$/, "")}${path}`;
}

async function request<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, { ...defaultFetchOptions, ...init });
  if (!response.ok) {
    let detail: string | undefined;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail;
    } catch {
      detail = undefined;
    }
    const message = detail ?? `Request failed (${response.status})`;
    throw new Error(message);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export interface TickSnapshot {
  timestamp: string;
  bid: number;
  ask: number;
  mid: number;
  liquidity_regime: string;
}

export interface InstrumentSnapshot {
  instrumentId: string;
  lastTick?: TickSnapshot;
}

interface MarketHealthResponse {
  status: string;
  instruments: Record<
    string,
    {
      last_tick?: TickSnapshot;
      liquidity_regime: string;
    }
  >;
}

export interface TradingHealthResponse {
  status: string;
}

export interface OrderPayload {
  instrument_id: string;
  side: "BUY" | "SELL";
  quantity: number;
  order_type: "MARKET" | "LIMIT";
  limit_price?: number;
}

export interface OrderResponseBody {
  order_id: string;
  instrument_id: string;
  side: "BUY" | "SELL";
  quantity: number;
  filled_quantity: number;
  status: "NEW" | "FILLED" | "PARTIALLY_FILLED";
  average_price?: number;
}

export interface SessionInfo {
  user_id: string;
  expires_at: string;
}

export async function fetchMarketHealth(): Promise<InstrumentSnapshot[]> {
  const url = buildUrl(marketDataBaseUrl, "/health");
  logger.info("ui.api.market_health", "Fetching market data health", { url });
  const payload = await request<MarketHealthResponse>(url, { method: "GET", credentials: "omit" });
  return Object.entries(payload.instruments ?? {}).map(([instrumentId, data]) => ({
    instrumentId,
    lastTick: data.last_tick
      ? {
          timestamp: data.last_tick.timestamp,
          bid: data.last_tick.bid,
          ask: data.last_tick.ask,
          mid: data.last_tick.mid,
          liquidity_regime: data.last_tick.liquidity_regime
        }
      : undefined
  }));
}

export async function fetchTradingHealth(): Promise<TradingHealthResponse> {
  const url = buildUrl(tradingBaseUrl, "/health");
  logger.info("ui.api.trading_health", "Fetching trading agent health", { url });
  return request<TradingHealthResponse>(url, { method: "GET" });
}

export async function submitOrder(payload: OrderPayload): Promise<OrderResponseBody> {
  const url = buildUrl(tradingBaseUrl, "/orders");
  logger.info("ui.api.order_submit", "Submitting order", { url, payload });
  return request<OrderResponseBody>(url, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export interface CredentialsPayload {
  email: string;
  password: string;
}

export async function login(payload: CredentialsPayload): Promise<SessionInfo> {
  const url = buildUrl(authBaseUrl, "/auth/login");
  logger.info("ui.api.login", "Logging in", { url, email: payload.email });
  return request<SessionInfo>(url, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function register(payload: CredentialsPayload): Promise<SessionInfo> {
  const url = buildUrl(authBaseUrl, "/auth/register");
  logger.info("ui.api.register", "Registering user", { url, email: payload.email });
  return request<SessionInfo>(url, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function logout(): Promise<void> {
  const url = buildUrl(authBaseUrl, "/auth/logout");
  logger.info("ui.api.logout", "Logging out", { url });
  await request<void>(url, { method: "POST" });
}

export async function fetchSession(): Promise<SessionInfo> {
  const url = buildUrl(authBaseUrl, "/auth/session");
  logger.info("ui.api.session", "Fetching session", { url });
  return request<SessionInfo>(url, { method: "GET" });
}

export const apiConfig = {
  marketDataBaseUrl,
  tradingBaseUrl,
  authBaseUrl
};
