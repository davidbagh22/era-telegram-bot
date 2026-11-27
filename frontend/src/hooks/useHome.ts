import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, fetchHome } from "../api/client";
import type { HomeSnapshot } from "../types/home";

type HomeState =
  | { status: "loading" }
  | { status: "ready"; data: HomeSnapshot }
  | { status: "error"; detail: string };

export type HomeHookResult = HomeState & { reload: () => void };

const REVALIDATE_AFTER_MS = 30_000;

// Last good snapshot for this app session. Returning to Home from another
// screen (or re-opening the Mini App from Telegram) paints it immediately and
// refreshes in the background, instead of unmounting the whole screen into a
// skeleton and replaying every entrance animation on the next render.
let cachedHome: { data: HomeSnapshot; at: number } | null = null;

export function useHome(): HomeHookResult {
  const [state, setState] = useState<HomeState>(() =>
    cachedHome ? { status: "ready", data: cachedHome.data } : { status: "loading" },
  );
  const [tick, setTick] = useState(0);
  const stateRef = useRef(state);
  stateRef.current = state;

  const reload = useCallback(() => {
    setState({ status: "loading" });
    setTick((value) => value + 1);
  }, []);

  const load = useCallback((cancelled: () => boolean) => {
    fetchHome()
      .then((data) => {
        cachedHome = { data, at: Date.now() };
        if (!cancelled()) setState({ status: "ready", data });
      })
      .catch((error) => {
        if (cancelled()) return;
        // A failed background refresh must not replace content that is already shown.
        if (stateRef.current.status === "ready") return;
        const detail = error instanceof ApiError ? error.message : "unknown_error";
        setState({ status: "error", detail });
      });
  }, []);

  useEffect(() => {
    let cancelled = false;
    load(() => cancelled);
    return () => {
      cancelled = true;
    };
  }, [tick, load]);

  useEffect(() => {
    let cancelled = false;
    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      if (cachedHome && Date.now() - cachedHome.at < REVALIDATE_AFTER_MS) return;
      load(() => cancelled);
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [load]);

  return useMemo(() => ({ ...state, reload }), [state, reload]);
}
