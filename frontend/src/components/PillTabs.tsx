interface PillTabsProps<T extends string> {
  options: { value: T; label: string }[];
  active: T;
  onChange: (value: T) => void;
}

export function PillTabs<T extends string>({ options, active, onChange }: PillTabsProps<T>) {
  return (
    <div style={{ display: "flex", gap: "0.5rem", overflowX: "auto", paddingBottom: "0.25rem" }}>
      {options.map((option) => {
        const isActive = option.value === active;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            style={{
              flexShrink: 0,
              padding: "0.375rem 0.75rem",
              borderRadius: "999px",
              border: isActive ? "1px solid var(--era-red)" : "1px solid var(--era-border)",
              background: isActive ? "var(--era-red)" : "transparent",
              color: isActive ? "#fff" : "var(--era-text)",
              fontSize: "0.8125rem",
              fontFamily: "var(--era-font-body)",
            }}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
