import { CommunityIcon, EventIcon, HomeIcon, ProfileIcon, ProjectsIcon } from "./icons";

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
        position: "fixed",
        left: "max(0.75rem, env(safe-area-inset-left, 0px))",
        right: "max(0.75rem, env(safe-area-inset-right, 0px))",
        bottom: "calc(0.65rem + env(safe-area-inset-bottom, 0px))",
        maxWidth: 720,
        margin: "0 auto",
        display: "flex",
        gap: 2,
        padding: 5,
        background: "var(--era-glass)",
        border: "1px solid rgba(20,20,20,.075)",
        borderRadius: 24,
        boxShadow: "var(--era-shadow-dock)",
        backdropFilter: "blur(22px)",
        WebkitBackdropFilter: "blur(22px)",
        zIndex: 30,
      }}
    >
      {TABS.map(({ key, label, Icon }) => {
        const isActive = key === active;
        return (
          <button
            key={key}
            type="button"
            aria-label={label}
            aria-current={isActive ? "page" : undefined}
            onClick={() => onChange(key)}
            style={{
              position: "relative",
              flex: "1 1 0",
              minWidth: 0,
              minHeight: 54,
              padding: "0.4rem 0.08rem",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 2,
              border: 0,
              borderRadius: 19,
              background: isActive ? "rgba(227,38,54,.085)" : "transparent",
              color: isActive ? "var(--era-red)" : "#777a81",
              boxShadow: "none",
              fontSize: "0.62rem",
              fontWeight: isActive ? 850 : 700,
              transition: "background var(--era-motion-fast), color var(--era-motion-fast), transform var(--era-motion-tap)",
            }}
          >
            <span style={{ display: "flex", transform: isActive ? "scale(1.05)" : "scale(1)", transition: "transform var(--era-motion-fast)" }}>
              <Icon width={21} height={21} />
            </span>
            <span style={{ width: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
          </button>
        );
      })}
    </nav>
  );
}
