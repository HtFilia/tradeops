import { FormEvent, useState } from "react";
import { CredentialsPayload } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { logger } from "../lib/logging";

type Mode = "login" | "register";

export function LoginView(): JSX.Element {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [form, setForm] = useState<CredentialsPayload>({ email: "demo@example.com", password: "demo" });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const toggleMode = () => {
    setMode((prev) => (prev === "login" ? "register" : "login"));
    setError(null);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      logger.info("ui.auth.submit", "Submitting auth form", { mode, email: form.email });
      if (mode === "login") {
        await login(form);
      } else {
        await register(form);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Authentication failed";
      logger.error("ui.auth.failure", message, { mode });
      setError(message);
    }
    setSubmitting(false);
  };

  return (
    <div className="auth-shell">
      <div className="auth-panel">
        <header className="auth-header">
          <h1>Trading Board</h1>
          <p>
            Sign in to access market data, trading, and upcoming portfolio tools. Use demo credentials
            <strong> demo@example.com / demo</strong> to explore instantly.
          </p>
        </header>
        <form className="auth-form" onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={form.email}
              onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={form.password}
              onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
              minLength={8}
              required
            />
          </div>
          <button className="button button--primary" type="submit" disabled={submitting}>
            {submitting ? "Working…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
          {error ? (
            <p className="auth-feedback auth-feedback--error" role="alert">
              {error}
            </p>
          ) : (
            <p className="auth-feedback" />
          )}
        </form>
        <footer className="auth-footer">
          {mode === "login" ? (
            <span>
              Need an account?{" "}
              <button type="button" className="link-button" onClick={toggleMode}>
                Register
              </button>
            </span>
          ) : (
            <span>
              Already have an account?{" "}
              <button type="button" className="link-button" onClick={toggleMode}>
                Sign in
              </button>
            </span>
          )}
        </footer>
      </div>
    </div>
  );
}
