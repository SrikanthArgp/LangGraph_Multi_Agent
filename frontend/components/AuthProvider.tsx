"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { apiFetch, ApiError, setAccessToken, setRefreshHandler } from "@/lib/api";

const REFRESH_TOKEN_STORAGE_KEY = "crag_refresh_token";
// Refresh at 80% of the access token's TTL, per plan.md's silent-refresh design.
const REFRESH_MARGIN_RATIO = 0.8;
const MIN_REFRESH_DELAY_MS = 5000;

export interface AuthUser {
  id: string;
  email: string;
  username: string;
  is_active: boolean;
  created_at: string;
}

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

interface AuthResponse {
  tokens: TokenResponse;
  user: AuthUser;
}

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function getStoredRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
}

function storeRefreshToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, token);
  else window.localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
}

function messageFromError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inFlightRefreshRef = useRef<Promise<string | null> | null>(null);
  // setTimeout's callback is created before performRefresh exists (circular dependency:
  // applyTokens schedules a timer that calls performRefresh, which calls applyTokens on
  // success) — a ref sidesteps that by resolving the current function only when the timer fires.
  const performRefreshRef = useRef<() => Promise<string | null>>(() => Promise.resolve(null));

  const clearRefreshTimer = useCallback(() => {
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  const scheduleRefresh = useCallback(
    (expiresInSeconds: number) => {
      clearRefreshTimer();
      const delayMs = Math.max(expiresInSeconds * REFRESH_MARGIN_RATIO * 1000, MIN_REFRESH_DELAY_MS);
      refreshTimerRef.current = setTimeout(() => {
        void performRefreshRef.current();
      }, delayMs);
    },
    [clearRefreshTimer],
  );

  const applyTokens = useCallback(
    (tokens: TokenResponse) => {
      setAccessToken(tokens.access_token);
      storeRefreshToken(tokens.refresh_token);
      scheduleRefresh(tokens.expires_in);
    },
    [scheduleRefresh],
  );

  const performRefresh = useCallback(async (): Promise<string | null> => {
    if (inFlightRefreshRef.current) return inFlightRefreshRef.current;

    const attempt = (async (): Promise<string | null> => {
      const storedToken = getStoredRefreshToken();
      if (!storedToken) {
        setAccessToken(null);
        setUser(null);
        setStatus("unauthenticated");
        return null;
      }
      try {
        const tokens = await apiFetch<TokenResponse>(
          "/auth/refresh",
          { method: "POST", body: JSON.stringify({ refresh_token: storedToken }) },
          { auth: false },
        );
        applyTokens(tokens);
        setStatus("authenticated");
        return tokens.access_token;
      } catch {
        // Expired/revoked/unreadable refresh token — only recovery is a fresh login.
        setAccessToken(null);
        storeRefreshToken(null);
        setUser(null);
        setStatus("unauthenticated");
        return null;
      }
    })();

    inFlightRefreshRef.current = attempt;
    try {
      return await attempt;
    } finally {
      inFlightRefreshRef.current = null;
    }
  }, [applyTokens]);

  useEffect(() => {
    performRefreshRef.current = performRefresh;
  }, [performRefresh]);

  useEffect(() => {
    setRefreshHandler(performRefresh);
    return () => setRefreshHandler(null);
  }, [performRefresh]);

  // On mount (including a hard reload): the access token never survives a reload by
  // design, so recover a session purely from the refresh token in localStorage.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const newAccessToken = await performRefresh();
      if (cancelled || !newAccessToken) return;
      try {
        const me = await apiFetch<AuthUser>("/auth/me");
        if (!cancelled) setUser(me);
      } catch {
        // Transient /me failure after a valid refresh — leave the session authenticated
        // rather than forcing a logout over what's likely a network blip.
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => clearRefreshTimer, [clearRefreshTimer]);

  const login = useCallback(
    async (email: string, password: string) => {
      setError(null);
      try {
        const data = await apiFetch<AuthResponse>(
          "/auth/login",
          { method: "POST", body: JSON.stringify({ email, password }) },
          { auth: false },
        );
        applyTokens(data.tokens);
        setUser(data.user);
        setStatus("authenticated");
      } catch (err) {
        setStatus("unauthenticated");
        setError(messageFromError(err, "Login failed. Please try again."));
        throw err;
      }
    },
    [applyTokens],
  );

  const register = useCallback(
    async (email: string, username: string, password: string) => {
      setError(null);
      try {
        const data = await apiFetch<AuthResponse>(
          "/auth/register",
          { method: "POST", body: JSON.stringify({ email, username, password }) },
          { auth: false },
        );
        applyTokens(data.tokens);
        setUser(data.user);
        setStatus("authenticated");
      } catch (err) {
        setStatus("unauthenticated");
        setError(messageFromError(err, "Registration failed. Please try again."));
        throw err;
      }
    },
    [applyTokens],
  );

  const logout = useCallback(async () => {
    const storedToken = getStoredRefreshToken();
    try {
      await apiFetch<void>("/auth/logout", {
        method: "POST",
        body: JSON.stringify(storedToken ? { refresh_token: storedToken } : {}),
      });
    } catch {
      // Best-effort server-side revocation — local state is cleared unconditionally below.
    } finally {
      clearRefreshTimer();
      setAccessToken(null);
      storeRefreshToken(null);
      setUser(null);
      setStatus("unauthenticated");
    }
  }, [clearRefreshTimer]);

  const clearError = useCallback(() => setError(null), []);

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, error, login, register, logout, clearError }),
    [status, user, error, login, register, logout, clearError],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
