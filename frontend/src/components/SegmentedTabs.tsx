interface SegmentedTabsProps<T extends string> {
  options: { value: T; label: string }[];
  active: T;
  onChange: (value: T) => void;
}

/** Primary, page-level section switcher — "which screen am I on" (e.g.
 * ActivityScreen's События/Задачи/Календарь/История). Full-width, equal
 * segments inside a single filled track, so it reads as one structural
 * control rather than a row of buttons — and visually outranks any
 * secondary filter (see FilterChips) stacked underneath it, instead of
 * both looking like the same repeated slider. Not meant for long or
 * open-ended option lists (use PillTabs there) — segments shrink to fit
 * rather than scroll. */
export function SegmentedTabs<T extends string>({ options, active, onChange }: SegmentedTabsProps<T>) {
  return (
    <div
      role="tablist"
      style={{
        display: "flex",
        gap: "0.125rem",
        padding: "0.25rem",
        background: "var(--era-surface-2)",
        borderRadius: "var(--era-radius-pill)",
      }}
    >
      {options.map((option) => {
        const isActive = option.value === active;
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(option.value)}
            style={{
              flex: 1,
              minWidth: 0,
              minHeight: "auto",
              padding: "0.5rem 0.375rem",
              border: "none",
              borderRadius: "var(--era-radius-pill)",
              background: isActive ? "var(--era-gradient)" : "transparent",
              color: isActive ? "#fff" : "var(--era-text-muted)",
              fontSize: "0.8125rem",
              fontWeight: isActive ? 700 : 600,
              fontFamily: "var(--era-font-body)",
              boxShadow: isActive ? "0 4px 14px rgba(116, 44, 196, 0.3)" : "none",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              transition:
                "background var(--era-motion-fast), color var(--era-motion-fast), box-shadow var(--era-motion-fast)",
            }}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
