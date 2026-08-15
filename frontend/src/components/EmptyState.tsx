import { Card } from "./Card";
import { SecondaryButton } from "./Buttons";

interface EmptyStateProps {
  text?: string;
  title?: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function EmptyState({ text, title = "Пока здесь пусто", description, actionLabel, onAction }: EmptyStateProps) {
  const copy = description ?? text ?? "Новые данные появятся здесь после первого действия.";
  return (
    <Card style={{ background: "rgba(255,255,255,.62)", boxShadow: "none", textAlign: "left" }}>
      <strong style={{ display: "block", fontSize: "var(--era-text-lg)" }}>{title}</strong>
      <p style={{ color: "var(--era-text-muted)", fontSize: "0.875rem", margin: "0.35rem 0 0", lineHeight: 1.5 }}>{copy}</p>
      {actionLabel && onAction && <SecondaryButton onClick={onAction} style={{ marginTop: "0.8rem" }}>{actionLabel}</SecondaryButton>}
    </Card>
  );
}
