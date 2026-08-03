interface StatusBadgeProps {
  label: string;
  tone?: "neutral" | "violet" | "red";
}

const TONE_COLORS: Record<NonNullable<StatusBadgeProps["tone"]>, string> = {
  neutral: "var(--era-text-muted)",
  violet: "var(--era-violet)",
  red: "var(--era-red)",
};

export function StatusBadge({ label, tone = "neutral" }: StatusBadgeProps) {
  const color = TONE_COLORS[tone];
  return (
    <span
      style={{
        display: "inline-block",
        fontSize: "0.75rem",
        fontWeight: 600,
        padding: "0.125rem 0.5rem",
        borderRadius: "999px",
        color,
        border: `1px solid ${color}`,
      }}
    >
      {label}
    </span>
  );
}
