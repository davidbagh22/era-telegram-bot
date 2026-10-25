import type { ReactNode } from "react";
import { MonoLabel } from "./MonoLabel";

interface FocusCardProps {
  eyebrow: string;
  title: ReactNode;
  actionLabel: ReactNode;
  meta?: ReactNode;
  onClick?: () => void;
  visual?: ReactNode;
}

/**
 * "Твой фокус" (ToR §10): one large light card showing a single main
 * action, not a checklist. Label + title + action line, a visual on the
 * right, a circular arrow button.
 */
export function FocusCard({ eyebrow, title, actionLabel, meta, onClick, visual }: FocusCardProps) {
  const Wrapper = onClick ? "button" : "div";
  return (
    <Wrapper
      type={onClick ? "button" : undefined}
      onClick={onClick}
      className="era-card"
      style={{
        width: "100%",
        textAlign: "left",
        borderRadius: "var(--era-radius-xl)",
        padding: "1.5rem",
        border: "1px solid var(--era-border)",
        background: "var(--era-surface)",
        boxShadow: "var(--era-shadow-soft)",
        display: "flex",
        alignItems: "center",
        gap: "1rem",
      }}
    >
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: "0.6rem" }}>
        <MonoLabel tone="violet">{eyebrow}</MonoLabel>
        <strong
          style={{
            fontFamily: "var(--era-font-display)",
            fontSize: "1.3rem",
            fontWeight: 800,
            lineHeight: 1.15,
            letterSpacing: "-0.015em",
          }}
        >
          {title}
        </strong>
        <div style={{ color: "var(--era-text-secondary)", fontSize: "var(--era-text-sm)", display: "flex", flexDirection: "column", gap: "0.1rem" }}>
          {actionLabel}
          {meta && <span style={{ color: "var(--era-text-muted-token, var(--era-text-faint))" }}>{meta}</span>}
        </div>
      </div>

      <div style={{ flexShrink: 0, display: "flex", flexDirection: "column", alignItems: "center", gap: "0.6rem" }}>
        {visual}
        <span
          aria-hidden="true"
          style={{
            width: 44,
            height: 44,
            borderRadius: "50%",
            display: "grid",
            placeItems: "center",
            background: "var(--era-gradient-signal)",
            color: "#fff",
            fontSize: "1.1rem",
            fontWeight: 800,
            boxShadow: "var(--era-glow-violet)",
          }}
        >
          →
        </span>
      </div>
    </Wrapper>
  );
}
