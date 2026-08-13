interface FilterChipsProps<T extends string> {
  options: { value: T; label: string }[];
  active: T;
  onChange: (value: T) => void;
}

/** Secondary, in-list filter — "which slice of this list am I looking
 * at" (e.g. EventsTab's Для меня/Все/Мои/Прошедшие). Deliberately quieter
 * than SegmentedTabs — outline chips with a tint fill on the active one,
 * no gradient — so a screen that stacks a SegmentedTabs section switcher
 * above one of these reads as two different kinds of control instead of
 * the same pill row repeated. Horizontally scrollable (scrollbar hidden,
 * see .era-pilltabs-scroller) for option lists too long to fit. */
export function FilterChips<T extends string>({ options, active, onChange }: FilterChipsProps<T>) {
  return (
    <div
      className="era-pilltabs-scroller"
      style={{
        display: "flex",
        gap: "0.375rem",
        overflowX: "auto",
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
            style={{
              flexShrink: 0,
              minHeight: "auto",
              padding: "0.3rem 0.7rem",
              borderRadius: "var(--era-radius-pill)",
              border: `1px solid ${isActive ? "var(--era-violet)" : "var(--era-border)"}`,
              background: isActive ? "var(--era-tint-violet)" : "transparent",
              color: isActive ? "var(--era-violet)" : "var(--era-text-muted)",
              fontSize: "0.75rem",
              fontWeight: isActive ? 700 : 500,
              fontFamily: "var(--era-font-body)",
              transition:
                "background var(--era-motion-fast), color var(--era-motion-fast), border-color var(--era-motion-fast)",
            }}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
