import type { ReactNode } from "react";

interface ActionCellProps {
  title: string;
  description?: string;
  meta?: ReactNode;
  leading?: ReactNode;
  onClick: () => void;
  active?: boolean;
}

/**
 * ERA's primary section-entry pattern. A full-width cell replaces horizontal
 * pill/segmented navigation and keeps section choices readable on narrow
 * Telegram viewports.
 */
export function ActionCell({
  title,
  description,
  meta,
  leading,
  onClick,
  active = false,
}: ActionCellProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      style={{
        width: "100%",
        minWidth: 0,
        minHeight: "4.5rem",
        padding: "0.875rem 1rem",
        display: "flex",
        alignItems: "center",
        gap: "0.875rem",
        textAlign: "left",
        borderRadius: "var(--era-radius-card)",
        border: active ? "1px solid rgba(99, 44, 255, 0.4)" : "1px solid var(--era-border)",
        background: active
          ? "linear-gradient(135deg, rgba(99, 44, 255, 0.12), rgba(255, 100, 0, 0.06)), var(--era-surface)"
          : "var(--era-surface)",
        boxShadow: "var(--era-shadow-soft)",
        color: "var(--era-text)",
      }}
    >
      {leading && (
        <span
          aria-hidden="true"
          style={{
            width: 42,
            height: 42,
            borderRadius: "50%",
            flexShrink: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--era-tint-violet)",
            color: "var(--era-violet)",
          }}
        >
          {leading}
        </span>
      )}
      <span style={{ flex: 1, minWidth: 0 }}>
        <strong
          style={{
            display: "block",
            fontSize: "var(--era-text-lg)",
            lineHeight: 1.25,
            overflowWrap: "anywhere",
          }}
        >
          {title}
        </strong>
        {description && (
          <span
            style={{
              display: "block",
              marginTop: "0.2rem",
              color: "var(--era-text-muted)",
              fontSize: "var(--era-text-sm)",
              fontWeight: 500,
              lineHeight: 1.35,
              overflowWrap: "anywhere",
            }}
          >
            {description}
          </span>
        )}
        {meta && (
          <span
            style={{
              display: "block",
              marginTop: "0.35rem",
              color: "var(--era-text-muted)",
              fontSize: "var(--era-text-xs)",
              fontWeight: 600,
            }}
          >
            {meta}
          </span>
        )}
      </span>
      <span aria-hidden="true" style={{ color: "var(--era-text-muted)", fontSize: "1.125rem", flexShrink: 0 }}>
        →
      </span>
    </button>
  );
}
