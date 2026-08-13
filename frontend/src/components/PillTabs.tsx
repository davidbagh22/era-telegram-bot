interface PillTabsProps<T extends string> {
  options: { value: T; label: string }[];
  active: T;
  onChange: (value: T) => void;
}

// Scrollable sibling of SegmentedTabs — same filled-track family (see
// tokens.css's era-pilltabs-scroller and SegmentedTabs.tsx), used where
// the option list is too long to fit as fixed equal segments (e.g.
// OpportunitiesScreen's 7 scopes, ProjectWorkspace's 7 tabs). The track
// background plus a right-edge fade mask (era-pilltabs-fade) reads as
// "this scrolls, and it's one control" instead of a loose row of pills
// floating on the page with a bare native scrollbar underneath.
export function PillTabs<T extends string>({ options, active, onChange }: PillTabsProps<T>) {
  return (
    <div
      className="era-pilltabs-scroller era-pilltabs-fade"
      style={{
        display: "flex",
        gap: "0.25rem",
        overflowX: "auto",
        padding: "0.25rem",
        background: "var(--era-surface-2)",
        borderRadius: "var(--era-radius-pill)",
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
              padding: "0.5rem 0.75rem",
              border: "none",
              borderRadius: "var(--era-radius-pill)",
              background: isActive ? "var(--era-gradient)" : "transparent",
              color: isActive ? "#fff" : "var(--era-text-muted)",
              fontSize: "0.8125rem",
              fontWeight: isActive ? 700 : 600,
              fontFamily: "var(--era-font-body)",
              boxShadow: isActive ? "0 4px 14px rgba(116, 44, 196, 0.3)" : "none",
              whiteSpace: "nowrap",
              transition: "background var(--era-motion-fast), color var(--era-motion-fast), box-shadow var(--era-motion-fast)",
            }}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
