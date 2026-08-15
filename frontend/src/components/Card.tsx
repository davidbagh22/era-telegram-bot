import type { CSSProperties, ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  gradient?: boolean;
  style?: CSSProperties;
  onClick?: () => void;
}

export function Card({ children, gradient = false, style, onClick }: CardProps) {
  const interactive = Boolean(onClick);
  const sharedStyle: CSSProperties = {
    borderRadius: "var(--era-radius-card)",
    padding: "1rem",
    border: gradient ? "1px solid rgba(227,38,54,0.10)" : "1px solid var(--era-border)",
    background: gradient ? "var(--era-hero-bg)" : "var(--era-surface)",
    boxShadow: gradient ? "0 12px 34px rgba(152,27,40,0.09)" : "var(--era-shadow-soft)",
    color: "var(--era-text)",
    ...style,
  };

  if (interactive) {
    return (
      <button
        type="button"
        className="era-card"
        onClick={onClick}
        style={{
          ...sharedStyle,
          width: "100%",
          minHeight: 44,
          textAlign: "left",
          fontWeight: 400,
        }}
      >
        {children}
      </button>
    );
  }

  return (
    <div className="era-card" style={sharedStyle}>
      {children}
    </div>
  );
}
