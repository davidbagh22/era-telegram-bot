interface PillTabsProps<T extends string> {
  options: { value: T; label: string }[];
  active: T;
  onChange: (value: T) => void;
}

export function PillTabs<T extends string>({ options, active, onChange }: PillTabsProps<T>) {
  return (
    <div
      className="era-pilltabs-scroller"
      style={{
        display: "flex",
        gap: "0.5rem",
        overflowX: "auto",
        // Without this, a flex item's default min-width is its content's
        // width, not 0 — with enough pills (OpportunitiesScreen has 7),
        // that's wider than a narrow phone, and since nothing here shrinks
        // it, the demand propagates up through every ancestor flex
        // container instead of staying contained by overflowX above.
        // Found by frontend/e2e/responsive.spec.ts at 320/360px.
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
              padding: "0.375rem 0.75rem",
              borderRadius: "999px",
              border: isActive ? "1px solid var(--era-red)" : "1px solid var(--era-border)",
              background: isActive ? "var(--era-gradient)" : "transparent",
              color: isActive ? "#fff" : "var(--era-text)",
              fontSize: "0.8125rem",
              fontWeight: isActive ? 700 : 500,
              fontFamily: "var(--era-font-body)",
              transform: isActive ? "scale(1.04)" : "scale(1)",
              transition: "transform var(--era-motion-fast), background var(--era-motion-fast), color var(--era-motion-fast), border-color var(--era-motion-fast)",
            }}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
