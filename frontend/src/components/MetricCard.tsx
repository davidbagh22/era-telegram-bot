import { Card } from "./Card";

export type MetricTone = "violet" | "red" | "gold" | "magenta";

interface MetricCardProps {
  label: string;
  value: string | number;
  /** Tinted background + tinted value color, for a row of metrics that
   * benefits from being told apart at a glance (HomeScreen's activity
   * grid). Omitted everywhere else (AdminDashboardScreen, OverviewTab,
   * ProjectWorkspace) — those stay the plain neutral card they always
   * were, unchanged. */
  tone?: MetricTone;
}

const TONE_STYLES: Record<MetricTone, { background: string; color: string }> = {
  violet: { background: "var(--era-tint-violet)", color: "var(--era-violet)" },
  red: { background: "var(--era-tint-red)", color: "var(--era-red)" },
  gold: { background: "var(--era-tint-gold)", color: "var(--era-gold-ink)" },
  magenta: { background: "var(--era-surface-2)", color: "var(--era-magenta)" },
};

export function MetricCard({ label, value, tone }: MetricCardProps) {
  const toneStyle = tone ? TONE_STYLES[tone] : undefined;
  return (
    <Card
      style={{
        textAlign: "center",
        // Only overridden when a tone is set — omitting the keys entirely
        // otherwise (rather than passing them as `undefined`) matters:
        // Card's own style object spreads its caller-supplied `style` last,
        // so an explicit `undefined` here would still win the spread and
        // strip Card's own default border/background instead of leaving
        // them alone.
        ...(toneStyle ? { background: toneStyle.background, border: "none" } : null),
      }}
    >
      <div
        style={{
          fontFamily: "var(--era-font-display)",
          fontSize: "1.5rem",
          fontWeight: 800,
          fontVariantNumeric: "tabular-nums",
          color: toneStyle?.color,
        }}
      >
        {value}
      </div>
      <div style={{ fontSize: "0.75rem", color: "var(--era-text-muted)", fontWeight: 600 }}>{label}</div>
    </Card>
  );
}
