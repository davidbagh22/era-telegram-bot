import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/client";

export type AsyncState<T> =
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "error"; detail: string };

export type AsyncHookResult<T> = AsyncState<T> & { reload: () => void };

export function useAsync<T>(fetcher: () => Promise<T>, deps: unknown[]): AsyncHookResult<T> {
  const [state, setState] = useState<AsyncState<T>>({ status: "loading" });
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => {
    setState({ status: "loading" });
    setTick((value) => value + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    fetcher()
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
    // fetcher is expected to be stable per the caller-provided deps array.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return { ...state, reload };
}
