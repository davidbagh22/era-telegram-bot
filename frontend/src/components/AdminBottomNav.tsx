import { CommsIcon, OverviewIcon, PeopleIcon, WorkIcon } from "./icons";

export type AdminGroup = "overview" | "people" | "work" | "comms";

// 2026-08 redesign brief section 34: "4 фиксированные группы, не 5" —
// the standalone Аналитика group folded into Обзор as a collapsible
// section (see AdminOverviewScreen.tsx), so this dock is down to 4.
const GROUPS: { key: AdminGroup; label: string; Icon: typeof OverviewIcon }[] = [
  { key: "overview", label: "Обзор", Icon: OverviewIcon },
  { key: "people", label: "Люди", Icon: PeopleIcon },
  { key: "work", label: "Работа", Icon: WorkIcon },
  { key: "comms", label: "Коммуникации", Icon: CommsIcon },
];

interface AdminBottomNavProps {
  active: AdminGroup;
  onChange: (group: AdminGroup) => void;
}

// 2026-08 master spec: Admin Mode's top-level navigation was a
// SegmentedTabs row (a long horizontal segmented control) — replaced with
// a fixed dock, the exact same floating-dock component and gradient-pill
// active state as the participant-facing BottomNavigation, just with its
// own 4 admin groups and icon set. Sub-navigation within a group (e.g.
// People's Участники/Заявки/Должности/Удаление данных) stays on
// FilterChips — that's 2-4 short, non-scrolling options for choosing a
// sub-screen, not the "long primary nav row" or "list filter" patterns
// the spec singles out, so it's unaffected by this change.
export function AdminBottomNav({ active, onChange }: AdminBottomNavProps) {
  return (
    <nav
      style={{
        position: "sticky",
        bottom: 0,
        display: "flex",
        minWidth: 0,
        gap: "0.125rem",
        margin: "0 0.75rem calc(0.6rem + env(safe-area-inset-bottom, 0px))",
        padding: "0.35rem",
        background: "var(--era-surface)",
        border: "1px solid var(--era-border)",
        borderRadius: "var(--era-radius-pill)",
        boxShadow: "var(--era-shadow-lift)",
      }}
    >
      {GROUPS.map(({ key, label, Icon }) => {
        const isActive = key === active;
        return (
          <button
            key={key}
            type="button"
            onClick={() => onChange(key)}
            aria-current={isActive ? "page" : undefined}
            style={{
              position: "relative",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "0.125rem",
              minHeight: "auto",
              flex: "1 1 0",
              minWidth: 0,
              background: "none",
              border: "none",
              color: isActive ? "#fff" : "var(--era-text-muted)",
              fontFamily: "var(--era-font-body)",
              fontSize: "0.6875rem",
              fontWeight: isActive ? 700 : 500,
              padding: "0.5rem 0.25rem",
              borderRadius: "var(--era-radius-pill)",
              transition: "color var(--era-motion-fast)",
              zIndex: 0,
            }}
          >
            {isActive && (
              <span
                aria-hidden="true"
                style={{
                  position: "absolute",
                  inset: 0,
                  borderRadius: "var(--era-radius-pill)",
                  background: "linear-gradient(135deg, var(--era-violet), var(--era-red))",
                  boxShadow: "0 8px 18px rgba(116, 44, 196, 0.4)",
                  zIndex: -1,
                }}
              />
            )}
            <Icon />
            <span
              style={{
                maxWidth: "100%",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {label}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
