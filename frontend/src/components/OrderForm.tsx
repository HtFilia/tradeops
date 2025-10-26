import { FormEvent, useEffect, useState } from "react";
import { OrderPayload } from "../lib/api";

interface OrderFormProps {
  onSubmit: (payload: OrderPayload) => Promise<void>;
  submitting: boolean;
  feedback: { message: string; tone: "success" | "error" | "idle" };
}

const DEFAULT_FORM: OrderPayload = {
  user_id: "demo-user",
  instrument_id: "EQ-ACME",
  side: "BUY",
  quantity: 100,
  order_type: "MARKET"
};

export function OrderForm({ onSubmit, submitting, feedback }: OrderFormProps) {
  const [formState, setFormState] = useState<OrderPayload>(DEFAULT_FORM);
  const [limitPrice, setLimitPrice] = useState<string>("");

  const handleChange = <Key extends keyof OrderPayload>(key: Key, value: OrderPayload[Key]) => {
    setFormState((prev) => ({
      ...prev,
      [key]: value
    }));
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const payload: OrderPayload = {
      ...formState,
      quantity: Number(formState.quantity)
    };

    if (payload.order_type === "LIMIT") {
      const parsed = Number(limitPrice);
      payload.limit_price = parsed > 0 && Number.isFinite(parsed) ? parsed : undefined;
    } else {
      payload.limit_price = undefined;
    }

    await onSubmit(payload);
  };

  const feedbackClass =
    feedback.tone === "success"
      ? "form-feedback form-feedback--success"
      : feedback.tone === "error"
      ? "form-feedback form-feedback--error"
      : "form-feedback";

  useEffect(() => {
    if (formState.order_type !== "LIMIT" && limitPrice !== "") {
      setLimitPrice("");
    }
  }, [formState.order_type, limitPrice]);

  return (
    <form className="form-grid" onSubmit={handleSubmit}>
      <div className="field">
        <label htmlFor="user-id">User ID</label>
        <input
          id="user-id"
          name="user_id"
          value={formState.user_id}
          onChange={(event) => handleChange("user_id", event.target.value)}
          required
        />
      </div>

      <div className="field">
        <label htmlFor="instrument-id">Instrument</label>
        <input
          id="instrument-id"
          name="instrument_id"
          placeholder="e.g. EQ-ACME"
          value={formState.instrument_id}
          onChange={(event) => handleChange("instrument_id", event.target.value)}
          required
        />
      </div>

      <div className="field field--inline">
        <div className="field">
          <label htmlFor="order-side">Side</label>
          <select
            id="order-side"
            name="side"
            value={formState.side}
            onChange={(event) => handleChange("side", event.target.value as OrderPayload["side"])}
          >
            <option value="BUY">Buy</option>
            <option value="SELL">Sell</option>
          </select>
        </div>

        <div className="field">
          <label htmlFor="order-type">Type</label>
          <select
            id="order-type"
            name="order_type"
            value={formState.order_type}
            onChange={(event) => handleChange("order_type", event.target.value as OrderPayload["order_type"])}
          >
            <option value="MARKET">Market</option>
            <option value="LIMIT">Limit</option>
          </select>
        </div>

        <div className="field">
          <label htmlFor="quantity">Quantity</label>
          <input
            id="quantity"
            name="quantity"
            type="number"
            min={1}
            value={formState.quantity}
            onChange={(event) => handleChange("quantity", Number(event.target.value))}
          />
        </div>
      </div>

      {formState.order_type === "LIMIT" ? (
        <div className="field">
          <label htmlFor="limit-price">Limit Price</label>
          <input
            id="limit-price"
            name="limit_price"
            type="number"
            min={0}
            step="0.01"
            value={limitPrice}
            onChange={(event) => setLimitPrice(event.target.value)}
            required
          />
        </div>
      ) : null}

      <button className="button button--primary" disabled={submitting} type="submit">
        {submitting ? "Submitting…" : "Submit order"}
      </button>

      <p className={feedbackClass} role="status">
        {feedback.message}
      </p>
    </form>
  );
}
