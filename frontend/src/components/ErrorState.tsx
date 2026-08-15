import { Card } from "./Card";
import { SecondaryButton } from "./Buttons";

interface ErrorStateProps {
  title?: string;
  description?: string;
  actionLabel?: string;
  onRetry?: () => void;
}

export function ErrorState({
  title = "Не получилось загрузить",
  description = "Проверьте соединение и попробуйте ещё раз.",
  actionLabel = "Повторить",
  onRetry,
}: ErrorStateProps) {
  return (
    <Card style={{ borderColor: "rgba(101,90,115,.18)", background: "rgba(101,90,115,.045)" }}>
      <strong style={{ display: "block", fontSize: "var(--era-text-lg)" }}>{title}</strong>
      <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)" }}>{description}</p>
      {onRetry && <SecondaryButton onClick={onRetry} style={{ marginTop: "0.8rem" }}>{actionLabel}</SecondaryButton>}
    </Card>
  );
}
