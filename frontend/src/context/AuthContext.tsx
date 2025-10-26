import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  ReactNode
} from "react";
import { CredentialsPayload, fetchSession, login, logout, register, SessionInfo } from "../lib/api";
import { logger } from "../lib/logging";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthState {
  user: SessionInfo | null;
  status: AuthStatus;
  login: (credentials: CredentialsPayload) => Promise<void>;
  register: (credentials: CredentialsPayload) => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }): JSX.Element {
  const [user, setUser] = useState<SessionInfo | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  const loadSession = useCallback(async () => {
    setStatus("loading");
    try {
      const session = await fetchSession();
      setUser(session);
      setStatus("authenticated");
    } catch (error) {
      logger.warn("ui.auth.session_missing", "No active session", {
        error: error instanceof Error ? error.message : String(error)
      });
      setUser(null);
      setStatus("unauthenticated");
    }
  }, []);

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

  const handleLogin = useCallback(async (credentials: CredentialsPayload) => {
    const session = await login(credentials);
    setUser(session);
    setStatus("authenticated");
  }, []);

  const handleRegister = useCallback(async (credentials: CredentialsPayload) => {
    const session = await register(credentials);
    setUser(session);
    setStatus("authenticated");
  }, []);

  const handleLogout = useCallback(async () => {
    await logout();
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      status,
      login: async (credentials) => {
        await handleLogin(credentials);
      },
      register: async (credentials) => {
        await handleRegister(credentials);
      },
      logout: async () => {
        await handleLogout();
      },
      refreshSession: loadSession
    }),
    [user, status, handleLogin, handleRegister, handleLogout, loadSession]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
