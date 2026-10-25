interface FilterChipsProps<T extends string> {
  options: { value: T; label: string }[];
  active: T;
  onChange: (value: T) => void;
}

/** Secondary list filter. Options wrap on narrow screens instead of creating
 * a horizontal scroller; section navigation belongs in ActionCell. */
export function FilterChips<T extends string>({ options, active, onChange }: FilterChipsProps<T>) {
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
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
            aria-pressed={isActive}
            style={{
              flex: "0 1 auto",
              maxWidth: "100%",
              minHeight: "2.5rem",
              padding: "0.5rem 0.75rem",
              borderRadius: "var(--era-radius-control)",
              border: `1px solid ${isActive ? "rgba(99, 44, 255, 0.5)" : "var(--era-border)"}`,
              background: isActive ? "var(--era-tint-violet)" : "var(--era-surface-2)",
              color: isActive ? "var(--era-text)" : "var(--era-text-muted)",
              fontSize: "var(--era-text-xs)",
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
