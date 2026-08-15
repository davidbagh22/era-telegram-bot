import {
  CommunityIcon,
  EventIcon,
  HomeIcon,
  ProfileIcon,
  ProjectsIcon,
} from "./icons";

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
        gap: "0.125rem",
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
            aria-label={label}
            style={{
              position: "relative",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: "0.1rem",
              minHeight: 52,
              flex: "1 1 0",
              minWidth: 0,
              background: "transparent",
              border: "none",
              boxShadow: "none",
              color: isActive ? "var(--era-red)" : "var(--era-text-muted)",
              fontSize: "0.625rem",
              fontWeight: isActive ? 800 : 650,
              padding: "0.4rem 0.125rem",
              borderRadius: "1.25rem",
              transition: "color var(--era-motion-fast), transform var(--era-motion-fast), background var(--era-motion-fast)",
            }}
          >
            <span
              aria-hidden="true"
              style={{
                display: "grid",
                placeItems: "center",
                width: 34,
                height: 28,
                borderRadius: "var(--era-radius-pill)",
                background: isActive ? "rgba(227,38,54,0.09)" : "transparent",
                transform: isActive ? "scale(1.05)" : "scale(1)",
                transition: "transform var(--era-motion-fast), background var(--era-motion-fast)",
              }}
            >
              <Icon width={21} height={21} />
            </span>
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
