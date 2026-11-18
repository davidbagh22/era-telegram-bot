import { useCallback, useEffect, useState } from "react";
import { ApiError, fetchHome } from "../api/client";
import type { HomeSnapshot } from "../types/home";

type HomeState =
  | { status: "loading" }
  | { status: "ready"; data: HomeSnapshot }
  | { status: "error"; detail: string };

export type HomeHookResult = HomeState & { reload: () => void };

export function useHome(): HomeHookResult {
  const [state, setState] = useState<HomeState>({ status: "loading" });
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => {
    setState({ status: "loading" });
    setTick((value) => value + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchHome()
      .then((data) => {
        if (!cancelled) setState({ status: "ready", data });
      })
      .catch((error) => {
        if (cancelled) return;
        const detail = error instanceof ApiError ? error.message : "unknown_error";
        setState({ status: "error", detail });
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  return { ...state, reload };
}
