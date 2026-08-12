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

export function BottomNavigation({ active, onChange }: BottomNavigationProps) {
  return (
    <nav
      style={{
        position: "sticky",
        bottom: 0,
        display: "flex",
        // minWidth: 0 lets this actually shrink to the viewport instead of
        // demanding its unshrunk content width (5 labels' worth); without
        // it, the demand bleeds out through this and every ancestor flex
        // container up to <html> instead of staying contained here. See
        // PillTabs.tsx's comment for the same root cause. Found by
        // frontend/e2e/responsive.spec.ts at 320/360px — "Профиль", the
        // last tab, was landing past the viewport edge.
        minWidth: 0,
        padding: "0.5rem 0 calc(0.5rem + env(safe-area-inset-bottom, 0px))",
        background: "var(--era-bg)",
        borderTop: "1px solid var(--era-border)",
      }}
    >
      {TABS.map(({ key, label, Icon }) => {
        const isActive = key === active;
        const color = isActive ? "var(--era-red)" : "var(--era-text-muted)";
        return (
          <button
            key={key}
            type="button"
            onClick={() => onChange(key)}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "0.125rem",
              minHeight: "auto",
              // flex: 1 1 0 + minWidth: 0 — five equal-share, genuinely
              // shrinkable columns instead of justify-content: space-around
              // over five unshrinkable ones; the label below truncates
              // with an ellipsis rather than forcing the bar (and the
              // whole page, see the <nav> comment above) wider than the
              // viewport on the narrowest phones.
              flex: "1 1 0",
              minWidth: 0,
              background: "none",
              border: "none",
              color,
              fontFamily: "var(--era-font-body)",
              fontSize: "0.6875rem",
              fontWeight: isActive ? 700 : 500,
              padding: "0.25rem 0.25rem",
              transform: isActive ? "translateY(-2px) scale(1.08)" : "translateY(0) scale(1)",
              transition: "transform var(--era-motion-fast), color var(--era-motion-fast)",
            }}
          >
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
