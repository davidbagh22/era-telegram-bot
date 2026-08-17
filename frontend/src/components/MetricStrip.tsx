import type { ReactNode } from "react";

export type SignalTone = "violet" | "blue" | "magenta" | "orange";

const TONE_COLOR: Record<SignalTone, string> = {
  violet: "var(--era-violet)",
  blue: "var(--era-blue)",
  magenta: "var(--era-magenta)",
  orange: "var(--era-orange)",
};

const DEFAULT_ROTATION: SignalTone[] = ["violet", "orange", "blue", "magenta"];

interface SignalMetricProps {
  value: ReactNode;
  label: string;
  tone?: SignalTone;
  onClick?: () => void;
}

/** One big colored number + label, no card/border around it — the number
 * itself carries the weight (ToR §11). */
export function SignalMetric({ value, label, tone = "violet", onClick }: SignalMetricProps) {
  const content = (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.15rem", minWidth: 0 }}>
      <span
        style={{
          fontFamily: "var(--era-font-display)",
          fontSize: "clamp(1.75rem, 8vw, 2.25rem)",
          fontWeight: 800,
          lineHeight: 1,
          letterSpacing: "-0.03em",
          color: TONE_COLOR[tone],
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {value}
      </span>
      <span style={{ fontSize: "var(--era-text-sm)", color: "var(--era-text-secondary)", fontWeight: 600 }}>{label}</span>
    </div>
  );

  if (!onClick) return content;
  return (
    <button
      type="button"
      onClick={onClick}
      style={{ all: "unset", cursor: "pointer", minHeight: 44, display: "flex", alignItems: "center" }}
    >
      {content}
    </button>
  );
}

interface MetricStripProps {
  children: ReactNode;
}

/** "Сейчас в ЭРА" — one airy horizontal composition of SignalMetrics
 * instead of three heavy boxed cards (ToR §11). */
export function MetricStrip({ children }: MetricStripProps) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        gap: "1.25rem",
        flexWrap: "wrap",
      }}
    >
      {children}
    </div>
  );
}

export function defaultSignalTone(index: number): SignalTone {
  return DEFAULT_ROTATION[index % DEFAULT_ROTATION.length];
}
