import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

type ToastTone = "success" | "error" | "info";

interface ToastItem {
  id: number;
  tone: ToastTone;
  message: string;
}

interface ToastContextValue {
  show: (message: string, tone?: ToastTone) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const TONE_COLORS: Record<ToastTone, string> = {
  success: "var(--era-success)",
  error: "var(--era-error)",
  info: "var(--era-violet)",
};

const AUTO_DISMISS_MS = 3500;

/** Mount once at the app root (see main.tsx) — every screen calls
 * useToast().show(...) instead of a native alert(), which this codebase
 * has never used (a WebView `alert()` is jarring and blocks the whole
 * page). See docs/UI_DESIGN_SYSTEM.md. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(0);

  const show = useCallback((message: string, tone: ToastTone = "info") => {
    const id = nextId.current++;
    setToasts((current) => [...current, { id, tone, message }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, AUTO_DISMISS_MS);
  }, []);

  const value = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        style={{
          position: "fixed",
          top: "calc(0.75rem + env(safe-area-inset-top, 0px))",
          left: "0.75rem",
          right: "0.75rem",
          display: "flex",
          flexDirection: "column",
          gap: "0.5rem",
          zIndex: 60,
          pointerEvents: "none",
        }}
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className="era-toast"
            role="status"
            style={{
              borderRadius: "var(--era-radius-control)",
              background: "var(--era-surface)",
              boxShadow: "var(--era-shadow-lift)",
              borderLeft: `3px solid ${TONE_COLORS[toast.tone]}`,
              padding: "0.75rem 1rem",
              fontSize: "var(--era-text-base)",
              color: "var(--era-text)",
              pointerEvents: "auto",
            }}
          >
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast() must be used within a <ToastProvider>");
  }
  return context;
}
