import type { CSSProperties, ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  gradient?: boolean;
  style?: CSSProperties;
}

// The gradient variant is reserved for hero/growth/achievement moments —
// see docs/ERA_PLATFORM_PROGRESS.md design notes. Regular cards stay flat.
export function Card({ children, gradient = false, style }: CardProps) {
  return (
    <div
      style={{
        borderRadius: "var(--era-radius-card)",
        padding: "1rem",
        border: gradient ? "none" : "1px solid var(--era-border)",
        background: gradient ? "var(--era-gradient)" : "var(--era-surface)",
        boxShadow: gradient ? "none" : "var(--era-shadow-soft)",
        color: gradient ? "#fff" : "var(--era-text)",
        ...style,
      }}
    >
      {children}
    </div>
  );
}
