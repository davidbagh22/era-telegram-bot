import {
  CommunityIcon,
  EventIcon,
  HomeIcon,
  ProfileIcon,
  ProjectsIcon,
} from "./icons";

// ERA Dark Living System: participant navigation has five permanent
// product areas. Leader/Admin management remains outside this dock.
export type TabKey = "home" | "projects" | "events" | "community" | "profile";

const TABS: { key: TabKey; label: string; Icon: typeof HomeIcon }[] = [
  { key: "home", label: "Главная", Icon: HomeIcon },
  { key: "projects", label: "Проекты", Icon: ProjectsIcon },
  { key: "events", label: "События", Icon: EventIcon },
  { key: "community", label: "Сообщество", Icon: CommunityIcon },
  { key: "profile", label: "Профиль", Icon: ProfileIcon },
];

interface BottomNavigationProps {
  active: TabKey;
  onChange: (tab: TabKey) => void;
}

export function BottomNavigation({ active, onChange }: BottomNavigationProps) {
  return (
    <nav
      aria-label="Основная навигация"
      style={{
        position: "sticky",
        bottom: 0,
        display: "flex",
        minWidth: 0,
        gap: "0.0625rem",
        margin: "0 0.625rem calc(0.55rem + env(safe-area-inset-bottom, 0px))",
        padding: "0.3rem",
        background: "var(--era-glass)",
        border: "1px solid var(--era-border)",
        borderRadius: "var(--era-radius-pill)",
        boxShadow: "var(--era-shadow-dock)",
        backdropFilter: "blur(24px)",
        WebkitBackdropFilter: "blur(24px)",
        zIndex: 20,
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
              minHeight: "3rem",
              flex: "1 1 0",
              minWidth: 0,
              background: "none",
              border: "none",
              color: isActive ? "var(--era-text)" : "var(--era-text-muted)",
              fontFamily: "var(--era-font-body)",
              fontSize: "0.625rem",
              fontWeight: isActive ? 800 : 600,
              padding: "0.45rem 0.125rem",
              borderRadius: "1.35rem",
              transition: "color var(--era-motion-fast), transform var(--era-motion-fast)",
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
                  background:
                    "linear-gradient(180deg, rgba(255,255,255,0.16), rgba(255,255,255,0.04)), var(--era-gradient)",
                  boxShadow: "0 10px 24px rgba(227, 59, 73, 0.26)",
                  zIndex: -1,
                }}
              />
            )}
            <Icon width={22} height={22} />
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
