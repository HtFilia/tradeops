import { useCallback, useEffect, useMemo, useState } from "react";
import { InstrumentTable } from "./components/InstrumentTable";
import { OrderForm } from "./components/OrderForm";
import { StatusBadge } from "./components/StatusBadge";
import { ModuleCard } from "./components/ModuleCard";
import {
  OrderPayload,
  OrderResponseBody,
  fetchMarketHealth,
  fetchTradingHealth,
  submitOrder,
  InstrumentSnapshot
} from "./lib/api";
import { logger } from "./lib/logging";
import { usePolling } from "./hooks/usePolling";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { LoginView } from "./views/LoginView";

type StatusState = "idle" | "ok" | "error";

const MARKET_REFRESH_MS = Number(import.meta.env.VITE_MARKET_REFRESH_MS ?? 2500);
const TRADING_REFRESH_MS = Number(import.meta.env.VITE_TRADING_REFRESH_MS ?? 10000);

function Dashboard(): JSX.Element {
  const { user, status, logout } = useAuth();
  const [marketStatus, setMarketStatus] = useState<StatusState>("idle");
  const [tradingStatus, setTradingStatus] = useState<StatusState>("idle");
  const [instruments, setInstruments] = useState<InstrumentSnapshot[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<{ message: string; tone: "success" | "error" | "idle" }>(
    {
      message: "",
      tone: "idle"
    }
  );

  const loadMarket = useCallback(async () => {
    if (status !== "authenticated") {
      return;
    }
    try {
      const snapshots = await fetchMarketHealth();
      setInstruments(snapshots);
      setMarketStatus("ok");
    } catch (error) {
      setMarketStatus("error");
      logger.error("ui.market.refresh_failed", "Failed to refresh market snapshots", {
        error: error instanceof Error ? error.message : String(error)
      });
    }
  }, [status]);

  const loadTrading = useCallback(async () => {
    if (status !== "authenticated") {
      return;
    }
    try {
      await fetchTradingHealth();
      setTradingStatus("ok");
    } catch (error) {
      setTradingStatus("error");
      logger.error("ui.trading.refresh_failed", "Trading service health check failed", {
        error: error instanceof Error ? error.message : String(error)
      });
    }
  }, [status]);

  useEffect(() => {
    if (status === "authenticated") {
      void loadMarket();
      void loadTrading();
    }
  }, [status, loadMarket, loadTrading]);

  usePolling(loadMarket, MARKET_REFRESH_MS);
  usePolling(loadTrading, TRADING_REFRESH_MS);

  const handleOrderSubmit = useCallback(async (payload: OrderPayload) => {
    setSubmitting(true);
    setFeedback({ message: "", tone: "idle" });
    try {
      const response: OrderResponseBody = await submitOrder(payload);
      setFeedback({
        message: `Order ${response.order_id} accepted (${response.status}).`,
        tone: "success"
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Order submission failed.";
      setFeedback({ message, tone: "error" });
    } finally {
      setSubmitting(false);
    }
  }, []);

  const marketStatusLabel = useMemo(() => {
    if (marketStatus === "ok") {
      return "Online";
    }
    if (marketStatus === "error") {
      return "Offline";
    }
    return "Checking…";
  }, [marketStatus]);

  const tradingStatusLabel = useMemo(() => {
    if (tradingStatus === "ok") {
      return "Online";
    }
    if (tradingStatus === "error") {
      return "Offline";
    }
    return "Checking…";
  }, [tradingStatus]);

  if (status === "loading") {
    return <div className="app-shell">Loading session…</div>;
  }

  if (status !== "authenticated" || user === null) {
    return <LoginView />;
  }

  const refreshManually = async () => {
    await Promise.allSettled([loadMarket(), loadTrading()]);
  };

  return (
    <div className="app-shell">
      <header className="header">
        <div>
          <h1 className="header__title">Trading Board</h1>
          <p className="header__subtitle">
            Welcome back. Monitor synthetic markets, submit orders, and preview upcoming portfolio and risk analytics.
          </p>
        </div>
        <div className="header-actions">
          <span className="header-actions__user">{user.user_id}</span>
          <button className="button button--ghost" type="button" onClick={() => logout()}>
            Log out
          </button>
        </div>
      </header>

      <section className="grid">
        <article className="panel">
          <div className="panel__header">
            <h2 className="panel__title">Market pulse</h2>
            <button className="button button--ghost" type="button" onClick={refreshManually}>
              Refresh
            </button>
          </div>
          <p className="panel__subtitle">
            Snapshots fetched from the market data agent. Live WebSocket streaming will replace polling once the
            gateway is ready.
          </p>
          <div className="status-line">
            <span>Market data service</span>
            <StatusBadge status={marketStatus} label={marketStatusLabel} />
          </div>
          <InstrumentTable instruments={instruments} />
        </article>

        <article className="panel">
          <div className="panel__header">
            <h2 className="panel__title">Quick trade</h2>
          </div>
          <p className="panel__subtitle">
            Submit rapid market or limit orders against the trading agent. Balance and position management happens in
            the backend using your authenticated session.
          </p>
          <div className="status-line">
            <span>Trading service</span>
            <StatusBadge status={tradingStatus} label={tradingStatusLabel} />
          </div>
          <OrderForm onSubmit={handleOrderSubmit} submitting={submitting} feedback={feedback} />
        </article>
      </section>

      <section className="module-grid">
        <ModuleCard
          title="Portfolio overview"
          description="Positions, P&L, and NAV snapshots will live here once the portfolio & risk agent comes online."
          badge="Coming soon"
        />
        <ModuleCard
          title="Risk & analytics"
          description="Delta, DV01, and scenario tools will plug into this workspace in later milestones."
          badge="Planned"
        />
        <ModuleCard
          title="Order activity"
          description="Executed trades, working orders, and OTC quote interactions will stream into this feed."
          badge="Planned"
        />
      </section>
    </div>
  );
}

export default function App(): JSX.Element {
  return (
    <AuthProvider>
      <Dashboard />
    </AuthProvider>
  );
}
