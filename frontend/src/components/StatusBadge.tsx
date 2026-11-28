interface StatusBadgeProps {
  label: string;
  tone?: "neutral" | "violet" | "red" | "gold" | "success";
}

const TONE_COLORS: Record<NonNullable<StatusBadgeProps["tone"]>, string> = {
  neutral: "var(--era-text-muted)",
  violet: "var(--era-violet)",
  red: "var(--era-red)",
  gold: "var(--era-gold, #f4c15d)",
  success: "var(--era-success, #55c89a)",
};

export function StatusBadge({ label, tone = "neutral" }: StatusBadgeProps) {
  const color = TONE_COLORS[tone];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        fontSize: "0.75rem",
        fontWeight: 600,
        lineHeight: 1.35,
        padding: "0.1875rem 0.5625rem",
        borderRadius: "999px",
        color,
        border: `1px solid ${color}`,
        whiteSpace: "nowrap",
        flexShrink: 0,
        maxWidth: "100%",
        overflow: "hidden",
        textOverflow: "ellipsis",
      }}
    >
      {label}
    </span>
  );
}
