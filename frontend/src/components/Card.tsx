import type { CSSProperties, ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  /** Soft violet/orange light field instead of a flat white surface —
   * for the one or two cards per screen that should read as "hero". */
  gradient?: boolean;
  /** Rare near-black accent card (ToR §7). Use sparingly. */
  dark?: boolean;
  style?: CSSProperties;
  onClick?: () => void;
}

export function Card({ children, gradient = false, dark = false, style, onClick }: CardProps) {
  const interactive = Boolean(onClick);
  const sharedStyle: CSSProperties = {
    borderRadius: "var(--era-radius-card)",
    padding: "1rem",
    border: dark ? undefined : gradient ? "1px solid rgba(99,44,255,0.16)" : "1px solid var(--era-border)",
    background: dark ? undefined : gradient ? "var(--era-hero-bg)" : "var(--era-surface)",
    boxShadow: dark ? "var(--era-shadow-lift)" : gradient ? "var(--era-shadow-lift)" : "var(--era-shadow-soft)",
    color: dark ? "#f7f5ff" : "var(--era-text)",
    ...style,
  };
  const className = dark ? "era-card era-card-dark" : gradient ? "era-card era-premium-ambient" : "era-card";

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
