import {
  ActivityIcon,
  HomeIcon,
  OpportunitiesIcon,
  ProfileIcon,
  ProjectsIcon,
} from "./icons";

export type TabKey = "home" | "activity" | "projects" | "opportunities" | "profile";

const TABS: { key: TabKey; label: string; Icon: typeof HomeIcon }[] = [
  { key: "home", label: "Главная", Icon: HomeIcon },
  { key: "activity", label: "Активность", Icon: ActivityIcon },
  { key: "projects", label: "Проекты", Icon: ProjectsIcon },
  { key: "opportunities", label: "Возможности", Icon: OpportunitiesIcon },
  { key: "profile", label: "Профиль", Icon: ProfileIcon },
];

interface BottomNavigationProps {
  active: TabKey;
  onChange: (tab: TabKey) => void;
}

// A floating "dock" instead of an edge-to-edge bar — inset from the sides
// so the page background shows around it, active tab gets a gradient pill
// fill instead of just a color/scale change. The overflow-safety technique
// (flex: 1 1 0 + minWidth: 0 per tab, label ellipsis) is unchanged from the
// bar version — that's what keeps "Возможности" from pushing the viewport
// wider at 320/360px (frontend/e2e/responsive.spec.ts), and nothing about
// the floating treatment touches it.
export function BottomNavigation({ active, onChange }: BottomNavigationProps) {
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
      {TABS.map(({ key, label, Icon }) => {
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
              // flex: 1 1 0 + minWidth: 0 — five equal-share, genuinely
              // shrinkable columns instead of justify-content: space-around
              // over five unshrinkable ones; the label below truncates
              // with an ellipsis rather than forcing the dock (and the
              // whole page) wider than the viewport on the narrowest
              // phones. See responsive.spec.ts.
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
