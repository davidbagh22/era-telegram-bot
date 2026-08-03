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
        const result = await authenticate(initData);
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
