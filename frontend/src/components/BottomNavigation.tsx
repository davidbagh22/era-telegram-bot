import {
  CommunityIcon,
  EventIcon,
  HomeIcon,
  ProfileIcon,
  ProjectsIcon,
} from "./icons";
import { selectionHaptic } from "../telegram/webApp";

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
  const activeIndex = Math.max(0, TABS.findIndex((tab) => tab.key === active));

  return (
    <nav
      aria-label="Основная навигация"
      style={{
        position: "sticky",
        bottom: 0,
        display: "grid",
        gridTemplateColumns: "repeat(5, minmax(0, 1fr))",
        minWidth: 0,
        margin: "0 0.625rem calc(0.55rem + env(safe-area-inset-bottom, 0px))",
        padding: "0.3rem",
        background: "var(--era-glass)",
        border: "1px solid var(--era-border)",
        borderRadius: "var(--era-radius-pill)",
        boxShadow: "var(--era-shadow-dock)",
        backdropFilter: "blur(24px)",
        WebkitBackdropFilter: "blur(24px)",
        overflow: "hidden",
        isolation: "isolate",
        zIndex: 20,
      }}
    >
      <span
        aria-hidden="true"
        style={{
          position: "absolute",
          left: "0.3rem",
          top: "0.3rem",
          bottom: "0.3rem",
          width: "calc((100% - 0.6rem) / 5)",
          borderRadius: "1.35rem",
          background: "linear-gradient(180deg, rgba(227,38,54,.14), rgba(227,38,54,.075))",
          border: "1px solid rgba(227,38,54,.13)",
          boxShadow: "inset 0 1px 0 rgba(255,255,255,.035)",
          transform: `translateX(${activeIndex * 100}%)`,
          transition: "transform 220ms cubic-bezier(0.22, 1, 0.36, 1)",
          zIndex: 0,
        }}
      />

      {TABS.map(({ key, label, Icon }) => {
        const isActive = key === active;
        return (
          <button
            key={key}
            type="button"
            onClick={() => {
              if (!isActive) selectionHaptic();
              onChange(key);
            }}
            aria-current={isActive ? "page" : undefined}
            aria-label={label}
            style={{
              position: "relative",
              zIndex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: "0.1rem",
              minHeight: 52,
              minWidth: 0,
              background: "transparent",
              border: "none",
              boxShadow: "none",
              color: isActive ? "var(--era-red-bright)" : "var(--era-text-muted)",
              fontSize: "0.625rem",
              fontWeight: isActive ? 800 : 650,
              padding: "0.4rem 0.125rem",
              borderRadius: "1.25rem",
              transition: "color var(--era-motion-fast), transform var(--era-motion-fast)",
            }}
          >
            <span
              aria-hidden="true"
              style={{
                position: "relative",
                display: "grid",
                placeItems: "center",
                width: 34,
                height: 28,
                borderRadius: "var(--era-radius-pill)",
                transform: isActive ? "scale(1.08)" : "scale(1)",
                transition: "transform var(--era-motion-fast)",
              }}
            >
              <Icon width={21} height={21} />
              <span
                style={{
                  position: "absolute",
                  bottom: -3,
                  width: isActive ? 12 : 4,
                  height: 2,
                  borderRadius: 999,
                  background: isActive ? "var(--era-red)" : "transparent",
                  opacity: isActive ? 1 : 0,
                  transition: "width 220ms cubic-bezier(0.22,1,0.36,1), opacity var(--era-motion-fast)",
                }}
              />
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
