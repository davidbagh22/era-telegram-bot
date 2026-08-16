import type { ReactNode } from "react";
import { ContextHelp } from "../components/ContextHelp";

interface LeaderLayoutProps {
  children: ReactNode;
  onExitWorkspace?: () => void;
}

export function LeaderLayout({ children, onExitWorkspace }: LeaderLayoutProps) {
  return (
    <div style={{ minHeight: "100vh", paddingTop: "env(safe-area-inset-top, 0px)" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "0.75rem",
          padding: "0.625rem 1.25rem",
          borderBottom: "1px solid var(--era-border)",
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem" }}>
          <strong style={{ fontFamily: "var(--era-font-display)", fontSize: "0.9375rem" }}>ЭРА</strong>
          <span style={{ fontSize: "0.75rem", color: "var(--era-violet)" }}>Лидер</span>
        </div>
        {onExitWorkspace && (
          <button
            type="button"
            onClick={onExitWorkspace}
            style={{
              minHeight: "auto",
              padding: "0.3rem 0.7rem",
              fontSize: "0.75rem",
              border: "1px solid var(--era-border)",
              background: "var(--era-surface)",
              borderRadius: "var(--era-radius-pill)",
            }}
          >
            ← Личное
          </button>
        )}
      </div>
      {children}
      <ContextHelp mode="leader" />
    </div>
  );
}
