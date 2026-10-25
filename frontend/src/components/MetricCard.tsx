import { Card } from "./Card";

export type MetricTone = "violet" | "red" | "gold" | "magenta";

interface MetricCardProps {
  label: string;
  value: string | number;
  /** Tinted background + tinted value color, for a row of metrics that
   * benefits from being told apart at a glance. */
  tone?: MetricTone;
  onClick?: () => void;
  hint?: string;
}

const TONE_STYLES: Record<MetricTone, { background: string; color: string }> = {
  violet: { background: "var(--era-tint-violet)", color: "var(--era-violet)" },
  red: { background: "var(--era-tint-red)", color: "var(--era-red)" },
  gold: { background: "var(--era-tint-gold)", color: "var(--era-gold-ink)" },
  magenta: { background: "var(--era-surface-2)", color: "var(--era-magenta)" },
};

export function MetricCard({ label, value, tone, onClick, hint }: MetricCardProps) {
  const toneStyle = tone ? TONE_STYLES[tone] : undefined;
  const card = (
    <Card
      style={{
        height: "100%",
        textAlign: "left",
        position: "relative",
        ...(toneStyle ? { background: toneStyle.background, border: "none" } : null),
      }}
    >
      <div
        style={{
          fontFamily: "var(--era-font-display)",
          fontSize: "1.75rem",
          lineHeight: 1,
          fontWeight: 850,
          fontVariantNumeric: "tabular-nums",
          color: toneStyle?.color,
        }}
      >
        {value}
      </div>
      <div style={{ marginTop: "0.4rem", fontSize: "0.8125rem", color: "var(--era-text)", fontWeight: 750 }}>{label}</div>
      {(hint || onClick) && (
        <div style={{ marginTop: "0.35rem", fontSize: "0.6875rem", color: "var(--era-text-muted)", fontWeight: 600 }}>
          {hint ?? "Открыть список →"}
        </div>
      )}
    </Card>
  );

  if (!onClick) return card;

  return (
    <button
      type="button"
      aria-label={`${label}: ${value}. Открыть список`}
      onClick={onClick}
      style={{
        all: "unset",
        display: "block",
        width: "100%",
        minWidth: 0,
        cursor: "pointer",
        WebkitTapHighlightColor: "transparent",
      }}
    >
      {card}
    </button>
  );
}
