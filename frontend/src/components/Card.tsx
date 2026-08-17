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
    border: gradient ? "1px solid rgba(227,38,54,0.14)" : "1px solid var(--era-border)",
    background: gradient ? "var(--era-hero-bg)" : "var(--era-surface)",
    boxShadow: gradient ? "0 16px 42px rgba(0,0,0,0.28)" : "var(--era-shadow-soft)",
    color: "var(--era-text)",
    ...style,
  };
  const className = gradient ? "era-card era-premium-ambient" : "era-card";

  if (interactive) {
    return (
      <button
        type="button"
        className={className}
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
    <div className={className} style={sharedStyle}>
      {children}
    </div>
  );
}
