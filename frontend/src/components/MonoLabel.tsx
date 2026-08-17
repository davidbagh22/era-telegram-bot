import type { CSSProperties, ReactNode } from "react";

export type MonoLabelTone = "default" | "violet" | "orange" | "onDark";

interface MonoLabelProps {
  children: ReactNode;
  tone?: MonoLabelTone;
  style?: CSSProperties;
}

const TONE_COLOR: Record<MonoLabelTone, string> = {
  default: "var(--era-text-secondary)",
  violet: "var(--era-violet)",
  orange: "var(--era-orange)",
  onDark: "rgba(247,245,255,0.68)",
};

/** Uppercase / mono-style technical label (ToR §8): "УРОВЕНЬ", "29 AUG",
 * "ТВОЙ ФОКУС". Not for running body text — the whole app must not go
 * uppercase, only these short technical tags. */
export function MonoLabel({ children, tone = "default", style }: MonoLabelProps) {
  return (
    <span className="era-mono-label" style={{ color: TONE_COLOR[tone], ...style }}>
      {children}
    </span>
  );
}
