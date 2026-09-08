import type { ReactNode } from "react";

interface ActionCellProps {
  title: string;
  description?: string;
  meta?: ReactNode;
  leading?: ReactNode;
  onClick: () => void;
  active?: boolean;
  compact?: boolean;
}

/**
 * ERA's primary section-entry pattern. The default is a full-width cell.
 * `compact` keeps the same visual language while making two-column admin
 * shortcuts readable on narrow Telegram/iPhone viewports.
 */
export function ActionCell({
  title,
  description,
  meta,
  leading,
  onClick,
  active = false,
  compact = false,
}: ActionCellProps) {
  const iconSize = compact ? 34 : 42;

  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      style={{
        width: "100%",
        minWidth: 0,
        minHeight: compact ? "5.25rem" : "4.5rem",
        padding: compact ? "0.75rem" : "0.875rem 1rem",
        display: "grid",
        gridTemplateColumns: leading
          ? `${iconSize}px minmax(0, 1fr) ${compact ? 14 : 18}px`
          : `minmax(0, 1fr) ${compact ? 14 : 18}px`,
        alignItems: "center",
        columnGap: compact ? "0.55rem" : "0.875rem",
        textAlign: "left",
        borderRadius: "var(--era-radius-card)",
        border: active ? "1px solid rgba(99, 44, 255, 0.4)" : "1px solid var(--era-border)",
        background: active
          ? "linear-gradient(135deg, rgba(99, 44, 255, 0.12), rgba(255, 100, 0, 0.06)), var(--era-surface)"
          : "var(--era-surface)",
        boxShadow: "var(--era-shadow-soft)",
        color: "var(--era-text)",
        overflow: "hidden",
      }}
    >
      {leading && (
        <span
          aria-hidden="true"
          style={{
            width: iconSize,
            height: iconSize,
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--era-tint-violet)",
            color: "var(--era-violet)",
            fontSize: compact ? "0.92rem" : undefined,
          }}
        >
          {leading}
        </span>
      )}
      <span style={{ minWidth: 0 }}>
        <strong
          style={{
            display: "block",
            fontSize: compact ? "0.9rem" : "var(--era-text-lg)",
            lineHeight: 1.2,
            overflowWrap: "normal",
            wordBreak: "normal",
            hyphens: "none",
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
              fontSize: compact ? "0.72rem" : "var(--era-text-sm)",
              fontWeight: 500,
              lineHeight: 1.3,
              overflowWrap: "normal",
              wordBreak: "normal",
              hyphens: "none",
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
      <span aria-hidden="true" style={{ color: "var(--era-text-muted)", fontSize: compact ? "0.95rem" : "1.125rem", justifySelf: "end" }}>
        →
      </span>
    </button>
  );
}
