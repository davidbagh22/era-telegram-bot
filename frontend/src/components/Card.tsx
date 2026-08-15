import type { CSSProperties, ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  gradient?: boolean;
  interactive?: boolean;
  onClick?: () => void;
  style?: CSSProperties;
  ariaLabel?: string;
}

export function Card({ children, gradient = false, interactive = false, onClick, style, ariaLabel }: CardProps) {
  const isInteractive = interactive || Boolean(onClick);
  return (
    <div
      className={`era-card${isInteractive ? " era-interactive" : ""}`}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      aria-label={ariaLabel}
      onClick={onClick}
      onKeyDown={onClick ? (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onClick(); } } : undefined}
      style={{
        borderRadius: "var(--era-radius-card)",
        padding: "1rem",
        border: gradient ? "1px solid rgba(152,27,40,.16)" : "1px solid var(--era-border)",
        background: gradient ? "var(--era-gradient)" : "var(--era-surface)",
        boxShadow: gradient ? "0 14px 34px rgba(152,27,40,.14)" : "var(--era-shadow-soft)",
        color: gradient ? "#fff" : "var(--era-text)",
        ...style,
      }}
    >
      {children}
    </div>
  );
}
