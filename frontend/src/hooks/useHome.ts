import { useEffect, useState } from "react";
import { ApiError, fetchHome } from "../api/client";
import type { HomeSnapshot } from "../types/home";

type HomeState =
  | { status: "loading" }
  | { status: "ready"; data: HomeSnapshot }
  | { status: "error"; detail: string };

export function useHome(): HomeState {
  const [state, setState] = useState<HomeState>({ status: "loading" });

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
  }, []);

  return state;
}
