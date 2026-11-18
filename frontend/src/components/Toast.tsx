import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

export type NotificationTone = "signal" | "attention" | "success" | "system";
type LegacyToastTone = "error" | "info";
type ToastTone = NotificationTone | LegacyToastTone;

interface ToastItem {
  id: number;
  tone: NotificationTone;
  message: string;
}

interface ToastContextValue {
  show: (message: string, tone?: ToastTone) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const TONE_COLORS: Record<NotificationTone, string> = {
  signal: "var(--era-violet)",
  attention: "var(--era-signal-red)",
  success: "var(--era-success)",
  system: "var(--era-blue)",
};

const TONE_LABELS: Record<NotificationTone, string> = {
  signal: "Сигнал",
  attention: "Внимание",
  success: "Готово",
  system: "Система",
};

const AUTO_DISMISS_MS = 3500;

export function normalizeToastTone(tone: ToastTone): NotificationTone {
  // Compatibility aliases keep existing call sites safe while the visual
  // system itself has one explicit semantic vocabulary.
  if (tone === "error") return "attention";
  if (tone === "info") return "system";
  return tone;
}

/** Mount once at the app root (see main.tsx) — every screen calls
 * useToast().show(...) instead of a native alert(), which this codebase
 * has never used (a WebView `alert()` is jarring and blocks the whole
 * page). See docs/UI_DESIGN_SYSTEM.md. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(0);
  const timers = useRef(new Map<number, number>());

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer != null) {
      window.clearTimeout(timer);
      timers.current.delete(id);
    }
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const show = useCallback((message: string, tone: ToastTone = "system") => {
    const id = nextId.current++;
    setToasts((current) => [...current, { id, tone: normalizeToastTone(tone), message }]);
    const timer = window.setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
    timers.current.set(id, timer);
  }, [dismiss]);

  useEffect(() => () => {
    for (const timer of timers.current.values()) window.clearTimeout(timer);
    timers.current.clear();
  }, []);

  const value = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-relevant="additions text"
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
            role={toast.tone === "attention" ? "alert" : "status"}
            aria-label={`${TONE_LABELS[toast.tone]}: ${toast.message}`}
            style={{
              borderRadius: "var(--era-radius-control)",
              background: "var(--era-surface)",
              boxShadow: "var(--era-shadow-lift)",
              borderLeft: `3px solid ${TONE_COLORS[toast.tone]}`,
              padding: "0.75rem 1rem",
              fontSize: "var(--era-text-base)",
              color: "var(--era-text)",
              pointerEvents: "auto",
              display: "grid",
              gridTemplateColumns: "1fr auto",
              gap: "0.65rem",
              alignItems: "start",
            }}
          >
            <div>
              <span
                style={{
                  display: "block",
                  marginBottom: "0.15rem",
                  color: TONE_COLORS[toast.tone],
                  fontSize: "0.68rem",
                  fontWeight: 800,
                  textTransform: "uppercase",
                  letterSpacing: "0.04em",
                }}
              >
                {TONE_LABELS[toast.tone]}
              </span>
              {toast.message}
            </div>
            <button
              type="button"
              aria-label="Закрыть уведомление"
              onClick={() => dismiss(toast.id)}
              style={{
                minWidth: 44,
                minHeight: 44,
                margin: "-0.35rem -0.35rem 0 0",
                padding: 0,
                border: 0,
                borderRadius: "50%",
                background: "transparent",
                color: "var(--era-text-muted)",
                fontSize: "1.1rem",
                lineHeight: 1,
                boxShadow: "none",
              }}
            >
              ×
            </button>
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
