import type { ReactNode } from "react";

interface EmptyStateProps {
  text: string;
  title?: string;
  actionLabel?: string;
  onAction?: () => void;
  children?: ReactNode;
}

/** Quiet empty / soft-error copy. Prefer this over ad-hoc muted paragraphs
 * so lists keep one voice and screen readers get a stable status region. */
export function EmptyState({ text, title, actionLabel, onAction, children }: EmptyStateProps) {
  return (
    <div
      role="status"
      style={{
        display: "grid",
        gap: "0.45rem",
        color: "var(--era-text-muted)",
        fontSize: "0.875rem",
      }}
    >
      {title ? (
        <strong style={{ color: "var(--era-text)", fontSize: "0.95rem", fontWeight: 700 }}>
          {title}
        </strong>
      ) : null}
      <p style={{ margin: 0 }}>{text}</p>
      {children}
      {actionLabel && onAction ? (
        <button
          type="button"
          className="era-btn-ghost"
          onClick={onAction}
          style={{ justifySelf: "start", minHeight: 44, paddingInline: "0.75rem" }}
        >
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}
