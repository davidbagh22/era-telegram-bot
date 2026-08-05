import { useEffect, useState } from "react";
import { ApiError, authenticate } from "../api/client";
import { getInitData, initTelegramWebApp } from "../telegram/webApp";
import type { MiniAppUserSummary } from "../types/auth";

type AuthState =
  | { status: "loading" }
  | { status: "ready"; user: MiniAppUserSummary }
  | { status: "error"; code: number; detail: string };

export function useAuth(): AuthState {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    initTelegramWebApp();

    async function run() {
      try {
        const initData = getInitData();
        // E2E-only hook: a real Telegram client never sets this query
        // param, and the backend ignores it entirely unless
        // DEV_AUTH_ENABLED is set (never true in production — see
        // Settings.assert_safe_for_deployment). Lets Playwright drive the
        // real built frontend as a specific seeded test user without a
        // real Telegram session.
        const devTelegramIdParam = new URLSearchParams(window.location.search).get(
          "devTelegramId",
        );
        const devTelegramId = devTelegramIdParam ? Number(devTelegramIdParam) : undefined;
        const result = await authenticate(initData, devTelegramId);
        if (!cancelled) {
          setState({ status: "ready", user: result.user });
        }
      } catch (error) {
        if (cancelled) return;
        if (error instanceof ApiError) {
          setState({ status: "error", code: error.status, detail: error.message });
        } else {
          setState({ status: "error", code: 0, detail: "unknown_error" });
        }
      }
    }

    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
