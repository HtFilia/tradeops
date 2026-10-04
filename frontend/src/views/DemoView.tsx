import { useEffect, useRef, useState } from "react";
import { useAuth } from "../context/AuthContext";
import {
  DemoAccount,
  DemoBook,
  DemoOrder,
  DemoReceipt,
  OrderPayload,
  readDemoAccount,
  readDemoBook,
  readDemoHistory,
  readDemoReceipt,
  resetDemo,
  executeDemo,
} from "../lib/api";
const money = (n: number | null) =>
  n === null
    ? "—"
    : n.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 6,
      });
const label = (s: string) => s.replaceAll("_", " ");
function Evidence(): JSX.Element {
  return (
    <nav aria-label="Technical evidence" className="demo-links">
      <a href="https://github.com/HtFilia/tradeops">Source & scope</a>
      <a href="https://github.com/HtFilia/tradeops/blob/master/trading/domain/matching.py">
        Matching engine
      </a>
      <a href="https://github.com/HtFilia/tradeops/blob/master/tests/demo/test_owned_execution.py">
        Transaction tests
      </a>
      <a href="https://lucaslebihan.dev">Portfolio</a>
    </nav>
  );
}
export function DemoLanding({ onLogin }: { onLogin: () => void }): JSX.Element {
  const { startDemo } = useAuth();
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function start() {
    setBusy(true);
    setError("");
    try {
      await startDemo();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="app-shell demo-landing">
      <span className="demo-eyebrow">TradeOps · execution investigation</span>
      <h1>Follow an order all the way through.</h1>
      <p className="demo-lead">
        See the liquidity, execute a simulated equity order, then reconcile
        every fill with cash and holdings.
      </p>
      <div className="demo-path" aria-label="Demo journey">
        <span>1 · Inspect depth</span>
        <span>2 · Execute</span>
        <span>3 · Reconcile</span>
      </div>
      <p>
        No registration. Your own temporary account starts with 10,000 synthetic
        USD. Nothing here is live trading.
      </p>
      <button className="button" disabled={busy} onClick={() => void start()}>
        {busy ? "Starting…" : "Try the isolated demo"}
      </button>
      <p role="alert">{error}</p>
      <section className="panel">
        <h2>Four outcomes. One inspectable engine.</h2>
        <p>
          Full fill · shallow book · non-crossing limit · position rejection
        </p>
        <p>
          Receipts persist through refresh for your two-hour session. Each order
          uses an immutable synthetic snapshot; residuals are final and never
          monitored.
        </p>
      </section>
      <Evidence />
      <button className="link-button" onClick={onLogin}>
        Existing account login / registration
      </button>
    </main>
  );
}
export function DemoView(): JSX.Element {
  const { logout } = useAuth();
  const [account, setAccount] = useState<DemoAccount | null>(null),
    [book, setBook] = useState<DemoBook | null>(null),
    [history, setHistory] = useState<DemoReceipt[]>([]),
    [selected, setSelected] = useState<DemoReceipt | null>(null),
    [draft, setDraft] = useState<OrderPayload>({
      instrument_id: "EQ-ACME",
      side: "BUY",
      quantity: 5,
      order_type: "MARKET",
    }),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [offset, setOffset] = useState(0),
    [notice, setNotice] = useState("");
  const revision = useRef(0),
    retry = useRef<DemoOrder | null>(null),
    resultHeading = useRef<HTMLHeadingElement>(null),
    caseHeading = useRef<HTMLHeadingElement>(null);
  async function refresh(preset = false, page = offset) {
    const version = ++revision.current;
    const [a, b, h] = await Promise.all([
      readDemoAccount(),
      readDemoBook(),
      readDemoHistory(page),
    ]);
    if (version !== revision.current) return;
    if (a.generation !== b.generation || a.generation !== h.generation)
      throw new Error("Case changed while loading. Reload the case.");
    setAccount(a);
    setBook(b);
    setHistory(h.receipts);
    if (preset) setDraft({ ...b.suggested_order, instrument_id: "EQ-ACME" });
  }
  useEffect(() => {
    void refresh(true, 0).catch((e) => setError(e.message));
    return () => {
      ++revision.current;
    };
  }, []);
  function edit(change: Partial<OrderPayload>) {
    retry.current = null;
    setError("");
    setDraft((d) => ({ ...d, ...change }));
  }
  async function reset(caseId: string) {
    if (!account) return;
    setBusy(true);
    setError("");
    ++revision.current;
    try {
      await resetDemo(account.generation, caseId);
      retry.current = null;
      setSelected(null);
      setOffset(0);
      await refresh(true, 0);
      setNotice(
        "Fresh case. Earlier receipts are archived until this session expires.",
      );
      requestAnimationFrame(() => caseHeading.current?.focus());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function execute() {
    if (!account || !book) return;
    setBusy(true);
    setError("");
    setNotice("");
    const payload = retry.current ?? {
      ...draft,
      generation: account.generation,
      snapshot_id: book.snapshot_id,
      idempotency_key: crypto.randomUUID(),
    };
    retry.current = payload;
    try {
      setSelected(await executeDemo(payload));
      retry.current = null;
      setOffset(0);
      await refresh(false, 0);
      requestAnimationFrame(() => resultHeading.current?.focus());
    } catch (e) {
      setError(
        (e as Error).message +
          " Retry preserves the request key; reload if the case changed.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function select(r: DemoReceipt) {
    setError("");
    try {
      setSelected(await readDemoReceipt(r.receipt_id));
      requestAnimationFrame(() => resultHeading.current?.focus());
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function pageHistory(next: number) {
    setBusy(true);
    try {
      await refresh(false, next);
      setOffset(next);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function download() {
    if (!selected) return;
    const url = URL.createObjectURL(
        new Blob([JSON.stringify(selected, null, 2)], {
          type: "application/json",
        }),
      ),
      a = document.createElement("a");
    a.href = url;
    a.download = `tradeops-${selected.case_id}-receipt.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  const levels = draft.side === "BUY" ? book?.book.asks : book?.book.bids;
  let remaining = draft.quantity,
    estimate = 0,
    estimateQty = 0;
  for (const [price, qty] of levels ?? []) {
    if (
      draft.order_type === "LIMIT" &&
      (draft.limit_price == null ||
        (draft.side === "BUY"
          ? price > draft.limit_price
          : price < draft.limit_price))
    )
      continue;
    const fill = Math.max(0, Math.min(remaining, qty));
    estimate += price * fill;
    estimateQty += fill;
    remaining -= fill;
  }
  const rejected =
    account &&
    (draft.side === "SELL"
      ? draft.quantity > account.account.holding
      : estimate > account.account.cash_balance);
  return (
    <main className="app-shell demo-workspace">
      <header className="app-header">
        <div>
          <span className="demo-eyebrow">TradeOps · isolated simulation</span>
          <h1>From depth to account.</h1>
          <p>EQ-ACME · USD · long only · no fees or margin</p>
        </div>
        <button
          className="button button--ghost"
          onClick={() => void logout().catch((e) => setError(e.message))}
        >
          End session
        </button>
      </header>
      <Evidence />
      <p className="demo-alert" role="alert">
        {error}
      </p>
      <p role="status">{notice}</p>
      {!account || !book ? (
        <section className="panel">
          <h2>Load your case</h2>
          <p>
            {error
              ? "Your session may have expired. End this session and start a new demo."
              : "Loading owned account and snapshot…"}
          </p>
          <button
            className="button"
            onClick={() =>
              void refresh(true, 0).catch((e) => setError(e.message))
            }
          >
            Reload case
          </button>
        </section>
      ) : (
        <>
          <section className="panel">
            <h2 ref={caseHeading} tabIndex={-1}>
              1 · Choose an outcome
            </h2>
            <div className="demo-cases">
              {book.cases.map((c) => (
                <button
                  key={c.case_id}
                  className="button button--ghost"
                  aria-pressed={c.case_id === account.case_id}
                  disabled={busy || account.remaining_resets === 0}
                  onClick={() => void reset(c.case_id)}
                >
                  {c.name}
                </button>
              ))}
            </div>
            <p>
              {
                book.cases.find((c) => c.case_id === account.case_id)
                  ?.description
              }
            </p>
            <div className="demo-metrics">
              <div>
                <span>Cash · synthetic USD</span>
                <strong data-testid="account-cash">
                  {money(account.account.cash_balance)}
                </strong>
              </div>
              <div>
                <span>Equity holding · shares</span>
                <strong data-testid="account-holding">
                  {account.account.holding}
                </strong>
              </div>
              <div>
                <span>Average cost · USD/share</span>
                <strong>{money(account.account.average_cost)}</strong>
              </div>
            </div>
            <p className="panel__subtitle">
              Session expires{" "}
              {new Date(account.expires_at).toLocaleTimeString()}.{" "}
              {account.remaining_submissions} submissions and{" "}
              {account.remaining_resets} resets left. Reset changes only your
              account.
            </p>
          </section>
          <section className="grid demo-grid">
            <article className="panel">
              <h2>2 · Inspect & execute</h2>
              <p>
                Best bid{" "}
                <strong>{money(book.book.bids[0]?.[0] ?? null)}</strong> / ask{" "}
                <strong>{money(book.book.asks[0]?.[0] ?? null)}</strong>{" "}
                USD/share
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void execute();
                }}
              >
                <fieldset disabled={busy}>
                  <div className="demo-form">
                    <label>
                      Side
                      <select
                        value={draft.side}
                        onChange={(e) =>
                          edit({ side: e.target.value as "BUY" | "SELL" })
                        }
                      >
                        <option>BUY</option>
                        <option>SELL</option>
                      </select>
                    </label>
                    <label>
                      Quantity · shares
                      <input
                        type="number"
                        min="1"
                        max="10000"
                        step="1"
                        required
                        value={draft.quantity}
                        onChange={(e) =>
                          edit({ quantity: Number(e.target.value) })
                        }
                      />
                    </label>
                    <label>
                      Order type
                      <select
                        value={draft.order_type}
                        onChange={(e) =>
                          edit({
                            order_type: e.target.value as "MARKET" | "LIMIT",
                            limit_price:
                              e.target.value === "LIMIT" ? 99.9 : undefined,
                          })
                        }
                      >
                        <option>MARKET</option>
                        <option>LIMIT</option>
                      </select>
                    </label>
                    {draft.order_type === "LIMIT" && (
                      <label>
                        Limit · USD/share
                        <input
                          type="number"
                          min="0.000001"
                          max="1000000"
                          step="any"
                          required
                          value={draft.limit_price ?? ""}
                          onChange={(e) =>
                            edit({ limit_price: Number(e.target.value) })
                          }
                        />
                      </label>
                    )}
                  </div>
                  <p className="demo-preview">
                    Snapshot preview: {estimateQty} filled / {draft.quantity}{" "}
                    requested · {money(estimate)} USD consideration
                    {rejected ? " · account check would reject" : ""}. Server
                    checks cash and holdings at execution.
                  </p>
                  <button
                    className="button"
                    type="submit"
                    disabled={account.remaining_submissions === 0}
                  >
                    {busy
                      ? "Executing…"
                      : retry.current
                        ? "Retry same request"
                        : "Execute snapshot order"}
                  </button>
                </fieldset>
              </form>
              <button
                className="link-button"
                disabled={busy}
                onClick={() => void reset(account.case_id)}
              >
                Reset this case
              </button>
            </article>
            <article className="panel">
              <details open>
                <summary>Supplied book depth · USD/share & shares</summary>
                <p>
                  Fixture {book.fixture_version}, dated {book.book.last_updated}
                  . Fixed fixture time; not a live market feed.
                </p>
                <div
                  className="table-wrapper"
                  role="region"
                  aria-label="Book depth"
                  tabIndex={0}
                >
                  <table>
                    <caption>Immutable liquidity reused per submission</caption>
                    <thead>
                      <tr>
                        <th>Side</th>
                        <th>Price</th>
                        <th>Available</th>
                        <th>Selected fill</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(["bids", "asks"] as const).flatMap((side) =>
                        book.book[side].map(([price, qty]) => (
                          <tr
                            key={`${side}-${price}`}
                            className={
                              selected?.generation === account.generation &&
                              selected.submitted.side ===
                                (side === "asks" ? "BUY" : "SELL") &&
                              selected.fills.some((f) => f.price === price)
                                ? "demo-filled"
                                : ""
                            }
                          >
                            <td>{side === "asks" ? "Ask" : "Bid"}</td>
                            <td>{money(price)}</td>
                            <td>{qty}</td>
                            <td>
                              {selected?.generation === account.generation &&
                              selected.submitted.side ===
                                (side === "asks" ? "BUY" : "SELL")
                                ? (selected.fills.find((f) => f.price === price)
                                    ?.quantity ?? 0)
                                : "—"}
                            </td>
                          </tr>
                        )),
                      )}
                    </tbody>
                  </table>
                </div>
              </details>
            </article>
          </section>
          <section className="panel" aria-label="Execution result">
            <h2 ref={resultHeading} tabIndex={-1}>
              3 · Reconcile the execution
            </h2>
            {!selected ? (
              <p>
                Execute the suggested order to see actual fills and committed
                account changes.
              </p>
            ) : (
              <>
                {selected.generation !== account.generation && (
                  <p>Archived receipt from an earlier case generation.</p>
                )}
                <p className="demo-outcome" role="status">
                  {label(selected.disposition)} · {selected.filled_quantity} /{" "}
                  {selected.submitted.quantity} shares filled
                </p>
                <p>
                  {selected.reason ??
                    (selected.residual_quantity
                      ? `${selected.residual_quantity} shares remain unfilled, final. This receipt is never monitored for a future fill.`
                      : "Every requested share filled against the supplied snapshot.")}
                </p>
                <p>
                  Consideration{" "}
                  <strong>{money(selected.consideration)} USD</strong> ·
                  weighted fill price{" "}
                  <strong>
                    {money(selected.average_fill_price)} USD/share
                  </strong>
                </p>
                <div
                  className="table-wrapper"
                  role="region"
                  aria-label="Fill detail"
                  tabIndex={0}
                >
                  <table>
                    <caption>Actual per-level fills</caption>
                    <thead>
                      <tr>
                        <th>Price · USD/share</th>
                        <th>Shares</th>
                        <th>Consideration · USD</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selected.fills.map((f, i) => (
                        <tr key={i}>
                          <td>{money(f.price)}</td>
                          <td>{f.quantity}</td>
                          <td>{money(f.price * f.quantity)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!selected.fills.length && <p>No fills.</p>}
                </div>
                <div
                  className="table-wrapper"
                  role="region"
                  aria-label="Cash and holdings reconciliation"
                  tabIndex={0}
                >
                  <table>
                    <caption>Recorded before / committed after</caption>
                    <thead>
                      <tr>
                        <th>Account measure</th>
                        <th>Before</th>
                        <th>After</th>
                        <th>Change</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <th>Cash · USD</th>
                        <td>{money(selected.before.cash_balance)}</td>
                        <td>{money(selected.after.cash_balance)}</td>
                        <td>
                          {money(
                            selected.after.cash_balance -
                              selected.before.cash_balance,
                          )}
                        </td>
                      </tr>
                      <tr>
                        <th>Holding · shares</th>
                        <td>{selected.before.holding}</td>
                        <td>{selected.after.holding}</td>
                        <td>
                          {selected.after.holding - selected.before.holding}
                        </td>
                      </tr>
                      <tr>
                        <th>Average cost · USD/share</th>
                        <td>{money(selected.before.average_cost)}</td>
                        <td>{money(selected.after.average_cost)}</td>
                        <td>Weighted buy cost</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <details>
                  <summary>Receipt conventions and identifiers</summary>
                  <p>{selected.conventions}</p>
                  <p className="demo-id">
                    Receipt {selected.receipt_id} · {selected.recorded_at}
                  </p>
                  <p className="demo-id">
                    Snapshot {selected.snapshot_id}; legacy status{" "}
                    {selected.legacy_status ?? "not an accepted order"}
                  </p>
                </details>
                <button className="button button--ghost" onClick={download}>
                  Download receipt JSON
                </button>
              </>
            )}
          </section>
          <section className="panel">
            <h2>Persisted history</h2>
            <p>
              Current case generation, newest first. Refresh preserves receipts
              until session expiry. Earlier generations are archived; owned
              receipt links remain readable.
            </p>
            {!history.length ? (
              <p>No receipts in this generation.</p>
            ) : (
              <div className="demo-history">
                {history.map((r) => (
                  <button
                    className="button button--ghost"
                    key={r.receipt_id}
                    disabled={busy}
                    onClick={() => void select(r)}
                  >
                    {r.submitted.side} {r.submitted.quantity} ·{" "}
                    {label(r.disposition)} ·{" "}
                    {new Date(r.recorded_at).toLocaleTimeString()}
                  </button>
                ))}
              </div>
            )}
            <div className="demo-pages">
              <button
                className="button button--ghost"
                disabled={busy || offset === 0}
                onClick={() => void pageHistory(Math.max(0, offset - 20))}
              >
                Newer receipts
              </button>
              <button
                className="button button--ghost"
                disabled={busy || history.length < 20}
                onClick={() => void pageHistory(offset + 20)}
              >
                Older receipts
              </button>
            </div>
          </section>
          <details className="panel">
            <summary>What this demonstrates / limits</summary>
            <p>{account.conventions}</p>
            <p>
              Only EQ-ACME supports execution. Bond yield and futures index
              quotes in the legacy feed are read-only. This case does not
              demonstrate a production exchange, risk engine, live portfolio
              valuation or reliable distributed event delivery.
            </p>
          </details>
        </>
      )}
    </main>
  );
}
