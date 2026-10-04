import { useCallback, useEffect, useMemo, useState } from "react";
import { InstrumentTable } from "./components/InstrumentTable";
import { OrderForm } from "./components/OrderForm";
import { StatusBadge } from "./components/StatusBadge";
import {
  fetchCapabilities,
  InstrumentCapability,
  OrderPayload,
  OrderResponseBody,
  fetchMarketHealth,
  fetchTradingHealth,
  submitOrder,
  InstrumentSnapshot,
} from "./lib/api";
import { logger } from "./lib/logging";
import { usePolling } from "./hooks/usePolling";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { DemoLanding, DemoView } from "./views/DemoView";
import { LoginView } from "./views/LoginView";
import { appendReceipt } from "./lib/orderActivity";

type StatusState = "idle" | "ok" | "error";

const MARKET_REFRESH_MS = Number(
  import.meta.env.VITE_MARKET_REFRESH_MS ?? 2500,
);
const TRADING_REFRESH_MS = Number(
  import.meta.env.VITE_TRADING_REFRESH_MS ?? 10000,
);

function Dashboard(): JSX.Element {
  const { user, status, logout } = useAuth();
  const [marketStatus, setMarketStatus] = useState<StatusState>("idle");
  const [tradingStatus, setTradingStatus] = useState<StatusState>("idle");
  const [capabilities, setCapabilities] = useState<InstrumentCapability[]>([]);
  const [instruments, setInstruments] = useState<InstrumentSnapshot[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [selectedInstrument, setSelectedInstrument] = useState("EQ-ACME");
  const [receipts, setReceipts] = useState<OrderResponseBody[]>([]);
  const [feedback, setFeedback] = useState<{
    message: string;
    tone: "success" | "error" | "idle";
  }>({
    message: "",
    tone: "idle",
  });

  const loadMarket = useCallback(async () => {
    if (status !== "authenticated") {
      return;
    }
    try {
      const [snapshots, caps] = await Promise.all([
        fetchMarketHealth(),
        fetchCapabilities(),
      ]);
      setCapabilities(caps);
      setInstruments(snapshots);
      setMarketStatus("ok");
    } catch (error) {
      setMarketStatus("error");
      logger.error(
        "ui.market.refresh_failed",
        "Failed to refresh market snapshots",
        {
          error: error instanceof Error ? error.message : String(error),
        },
      );
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
      logger.error(
        "ui.trading.refresh_failed",
        "Trading service health check failed",
        {
          error: error instanceof Error ? error.message : String(error),
        },
      );
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
      setReceipts((previous) => appendReceipt(previous, response));
      setFeedback({
        message: `Order ${response.order_id} accepted (${response.status}).`,
        tone: "success",
      });
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Order submission failed.";
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
          <h1 className="header__title">TradeOps</h1>
          <p className="header__subtitle">
            Select a synthetic instrument, submit a simulated order, and inspect
            its fill receipt. No real money.
          </p>
        </div>
        <div className="header-actions">
          <a href="https://lucaslebihan.dev/en/">Portfolio</a>{" "}
          <a href="https://github.com/HtFilia/tradeops/blob/master/trading/domain/matching.py">
            Matching source
          </a>
          <button
            className="button button--ghost"
            type="button"
            onClick={() => logout()}
          >
            Log out
          </button>
        </div>
      </header>

      <section className="grid">
        <article className="panel">
          <div className="panel__header">
            <h2 className="panel__title">Market pulse</h2>
            <button
              className="button button--ghost"
              type="button"
              onClick={refreshManually}
            >
              Refresh
            </button>
          </div>
          <p className="panel__subtitle">
            Synthetic quotes refresh every {MARKET_REFRESH_MS / 1000} seconds.
            Select an instrument to trade it.
          </p>
          <div className="status-line">
            <span>Market data service</span>
            <StatusBadge status={marketStatus} label={marketStatusLabel} />
          </div>
          <InstrumentTable
            instruments={instruments}
            selectedInstrument={selectedInstrument}
            onSelect={setSelectedInstrument}
            capabilities={capabilities}
          />
        </article>

        <article className="panel">
          <div className="panel__header">
            <h2 className="panel__title">Quick trade</h2>
          </div>
          <p className="panel__subtitle">
            Market orders use synthetic liquidity. Limit orders fill only when
            the current quote crosses your limit; an unfilled receipt is not a
            monitored working order. All funds and quotes are simulated; the
            demo login is shared.
          </p>
          <div className="status-line">
            <span>Trading service</span>
            <StatusBadge status={tradingStatus} label={tradingStatusLabel} />
          </div>
          <OrderForm
            onSubmit={handleOrderSubmit}
            submitting={submitting}
            feedback={feedback}
            selectedInstrument={selectedInstrument}
            instruments={capabilities
              .filter((item) => item.tradable)
              .map((item) => item.instrument_id)}
            onInstrumentChange={setSelectedInstrument}
          />
        </article>
      </section>

      <section className="panel" role="region" aria-label="Order activity">
        <h2 className="panel__title">Order activity</h2>
        <p className="panel__subtitle">
          Last ten submission receipts in this browser session. Refreshing or
          logging out clears this view; persisted orders remain on the server.
          This is not a live order status feed.
        </p>
        {receipts.length === 0 ? (
          <p>No orders submitted in this browser session.</p>
        ) : (
          <div
            className="table-wrapper"
            role="region"
            aria-label="Order receipts"
            tabIndex={0}
          >
            <table aria-label="Submission receipts">
              <thead>
                <tr>
                  <th>Instrument / side</th>
                  <th>Status at submission</th>
                  <th>Filled / requested</th>
                  <th>Average fill price</th>
                  <th>Order ID</th>
                </tr>
              </thead>
              <tbody>
                {receipts.map((receipt) => (
                  <tr key={receipt.order_id}>
                    <td>
                      {receipt.instrument_id} / {receipt.side}
                    </td>
                    <td>{receipt.status}</td>
                    <td>
                      {receipt.filled_quantity} / {receipt.quantity}
                    </td>
                    <td>
                      {receipt.average_price == null
                        ? "—"
                        : receipt.average_price.toFixed(4)}
                    </td>
                    <td>{receipt.order_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

export default function App(): JSX.Element {
  return (
    <AuthProvider>
      <SessionView />
    </AuthProvider>
  );
}

function SessionView(): JSX.Element {
  const { user, status } = useAuth();
  const [showLogin, setShowLogin] = useState(false);
  if (status === "loading")
    return <div className="app-shell">Loading session…</div>;
  if (status !== "authenticated" || user === null)
    return showLogin ? (
      <main>
        <button
          className="button button--ghost"
          onClick={() => setShowLogin(false)}
        >
          Back to isolated demo
        </button>
        <LoginView />
      </main>
    ) : (
      <DemoLanding onLogin={() => setShowLogin(true)} />
    );
  if (user.principal_kind === "guest") return <DemoView key={user.user_id} />;
  // Unmount the dashboard on logout so receipts and pending responses cannot
  // carry over to a later authenticated session.
  return <Dashboard key={user.user_id} />;
}
