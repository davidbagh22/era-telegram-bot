import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, authenticate, fetchMe } from "../api/client";
import { getInitData, initTelegramWebApp } from "../telegram/webApp";
import type { MiniAppUserSummary } from "../types/auth";

type AuthState =
  | { status: "loading" }
  | { status: "ready"; user: MiniAppUserSummary }
  | { status: "error"; code: number; detail: string };

export type UseAuthResult =
  | { status: "loading"; refresh: () => void }
  | { status: "ready"; user: MiniAppUserSummary; refresh: () => void }
  | { status: "error"; code: number; detail: string; refresh: () => void };

// Telegram may keep a Mini App's WebView alive in the background instead of
// reloading it when the user reopens it from the chat menu button or the
// bot's own button. A one-time auth check on mount then never notices a
// status change that happened while the app was backgrounded — e.g. an
// admin approving the application, or the participant only just finishing
// registration in the bot a moment before tapping the button — leaving the
// user stuck looking at a stale screen with no obvious way to recover short
// of fully closing Telegram. This polls while the outcome is still pending
// and re-checks whenever the WebView regains focus, instead of relying on a
// fresh page load.
const PENDING_POLL_INTERVAL_MS = 15_000;

function isPendingStatus(status: string): boolean {
  return status === "pending" || status === "needs_info";
}

export function useAuth(): UseAuthResult {
  const [state, setState] = useState<AuthState>({ status: "loading" });
  const stateRef = useRef(state);
  stateRef.current = state;
  const inFlightRef = useRef(false);

  const authenticateFresh = useCallback(async () => {
    const initData = getInitData();
    // E2E-only hook: a real Telegram client never sets this query param, and
    // the backend ignores it entirely unless DEV_AUTH_ENABLED is set (never
    // true in production — see Settings.assert_safe_for_deployment). Lets
    // Playwright drive the real built frontend as a specific seeded test
    // user without a real Telegram session.
    const devTelegramIdParam = new URLSearchParams(window.location.search).get("devTelegramId");
    const devTelegramId = devTelegramIdParam ? Number(devTelegramIdParam) : undefined;
    const result = await authenticate(initData, devTelegramId);
    setState({ status: "ready", user: result.user });
  }, []);

  const refresh = useCallback(async () => {
    if (inFlightRef.current) {
      return;
    }
    inFlightRef.current = true;
    try {
      if (stateRef.current.status === "ready") {
        // Already authenticated this session: a cheap re-check against the
        // existing token is enough to pick up a status change, and avoids
        // replaying an initData payload that may since have aged out of the
        // backend's freshness window. Falls back to a full re-authentication
        // only if the token itself expired or was never valid.
        try {
          const user = await fetchMe();
          setState({ status: "ready", user });
          return;
        } catch (error) {
          if (!(error instanceof ApiError) || error.status !== 401) {
            return; // transient failure (offline, 5xx) — keep showing what we already have
          }
          // token expired — fall through to a full re-authentication below
        }
      }
      try {
        await authenticateFresh();
      } catch (error) {
        if (error instanceof ApiError) {
          setState({ status: "error", code: error.status, detail: error.message });
        } else {
          setState({ status: "error", code: 0, detail: "unknown_error" });
        }
      }
    } finally {
      inFlightRef.current = false;
    }
  }, [authenticateFresh]);

  useEffect(() => {
    initTelegramWebApp();
    void refresh();
    // Intentionally runs once on mount — refresh() itself is stable and the
    // re-check triggers below (visibility/focus/polling) cover every other
    // case that needs a fresh look at auth state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    function onVisible() {
      if (document.visibilityState === "visible") {
        void refresh();
      }
    }
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [refresh]);

  useEffect(() => {
    if (state.status !== "ready" || !isPendingStatus(state.user.application_status)) {
      return;
    }
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void refresh();
      }
    }, PENDING_POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [state, refresh]);

  return { ...state, refresh: () => void refresh() };
}
