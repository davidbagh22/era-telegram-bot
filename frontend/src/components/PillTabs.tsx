interface PillTabsProps<T extends string> {
  options: { value: T; label: string }[];
  active: T;
  onChange: (value: T) => void;
}

/**
 * Legacy-compatible local selector. It intentionally wraps instead of
 * scrolling horizontally; primary navigation should use ActionCell.
 */
export function PillTabs<T extends string>({ options, active, onChange }: PillTabsProps<T>) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(8.5rem, 1fr))",
        gap: "0.5rem",
        width: "100%",
        minWidth: 0,
      }}
    >
      {options.map((option) => {
        const isActive = option.value === active;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            aria-current={isActive ? "page" : undefined}
            style={{
              minWidth: 0,
              width: "100%",
              minHeight: "2.75rem",
              padding: "0.625rem 0.75rem",
              border: `1px solid ${isActive ? "rgba(120, 61, 255, 0.55)" : "var(--era-border)"}`,
              borderRadius: "var(--era-radius-control)",
              background: isActive
                ? "linear-gradient(135deg, rgba(120,61,255,0.2), rgba(227,59,73,0.1)), var(--era-surface)"
                : "var(--era-surface)",
              color: isActive ? "var(--era-text)" : "var(--era-text-muted)",
              fontSize: "var(--era-text-sm)",
              fontWeight: isActive ? 800 : 600,
              overflowWrap: "anywhere",
            }}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
