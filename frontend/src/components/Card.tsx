import type { CSSProperties, ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  gradient?: boolean;
  style?: CSSProperties;
}

export function Card({ children, gradient = false, style }: CardProps) {
  return (
    <div
      className="era-card"
      style={{
        borderRadius: "var(--era-radius-card)",
        padding: "1rem",
        border: gradient ? "1px solid rgba(255,255,255,0.14)" : "1px solid var(--era-border)",
        background: gradient
          ? "radial-gradient(65% 85% at 92% 0%, rgba(255,255,255,0.20), transparent 55%), linear-gradient(180deg, rgba(255,255,255,0.10), rgba(255,255,255,0.015)), var(--era-gradient)"
          : "linear-gradient(180deg, rgba(255,255,255,0.045), rgba(255,255,255,0.018)), var(--era-surface)",
        boxShadow: gradient ? "var(--era-shadow-red)" : "var(--era-shadow-soft)",
        color: gradient ? "#fff" : "var(--era-text)",
        backdropFilter: "blur(18px)",
        WebkitBackdropFilter: "blur(18px)",
        ...style,
      }}
    >
      {children}
    </div>
  );
}
