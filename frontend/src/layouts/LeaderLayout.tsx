import type { ReactNode } from "react";

interface LeaderLayoutProps {
  children: ReactNode;
}

export function LeaderLayout({ children }: LeaderLayoutProps) {
  return (
    <div style={{ minHeight: "100vh", paddingTop: "env(safe-area-inset-top, 0px)" }}>
      <div
        style={{
          padding: "0.5rem 1rem",
          fontSize: "0.75rem",
          fontFamily: "var(--era-font-display)",
          letterSpacing: "0.05em",
          color: "var(--era-violet)",
        }}
      >
        ЭРА · ЛИДЕР
      </div>
      {children}
    </div>
  );
}
