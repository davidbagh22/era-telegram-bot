interface EmptyStateProps {
  text: string;
}

export function EmptyState({ text }: EmptyStateProps) {
  return (
    <p style={{ color: "var(--era-text-muted)", fontSize: "0.875rem", margin: 0 }}>{text}</p>
  );
}
