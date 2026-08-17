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
      className="era-bottom-nav"
      data-active-tab={active}
      style={{
        position: "fixed",
        left: "50%",
        bottom: "calc(0.55rem + env(safe-area-inset-bottom, 0px))",
        transform: "translateX(-50%)",
        width: "calc(100% - 1.25rem)",
        maxWidth: "32rem",
        display: "grid",
        gridTemplateColumns: "repeat(5, minmax(0, 1fr))",
        minWidth: 0,
        margin: 0,
        padding: "0.3rem",
        background: "var(--era-nav-glass, var(--era-glass))",
        border: "1px solid var(--era-nav-border, var(--era-border))",
        borderRadius: "var(--era-radius-pill)",
        boxShadow: "var(--era-shadow-dock)",
        backdropFilter: "blur(26px) saturate(118%)",
        WebkitBackdropFilter: "blur(26px) saturate(118%)",
        overflow: "hidden",
        isolation: "isolate",
        zIndex: 32,
      }}
    >
      <span
        aria-hidden="true"
        className="era-bottom-nav__selection"
        style={{
          position: "absolute",
          left: "0.3rem",
          top: "0.3rem",
          bottom: "0.3rem",
          width: "calc((100% - 0.6rem) / 5)",
          borderRadius: "1.35rem",
          background: "linear-gradient(180deg, rgba(227,38,54,.16), rgba(227,38,54,.075))",
          border: "1px solid rgba(227,38,54,.16)",
          boxShadow: "inset 0 1px 0 rgba(248,239,223,.055), 0 0 22px rgba(227,38,54,.045)",
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
              color: isActive ? "var(--era-red-bright)" : "var(--era-nav-muted, var(--era-text-muted))",
              fontSize: "0.625rem",
              fontWeight: isActive ? 800 : 650,
              padding: "0.4rem 0.125rem 0.48rem",
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
            <span
              aria-hidden="true"
              className="era-bottom-nav__active-mark"
              style={{
                position: "absolute",
                left: "50%",
                bottom: 2,
                width: isActive ? 24 : 6,
                height: 3,
                borderRadius: 999,
                background: isActive ? "var(--era-red-bright)" : "transparent",
                opacity: isActive ? 1 : 0,
                transform: "translateX(-50%)",
                boxShadow: isActive ? "0 0 10px rgba(255,64,80,.72), 0 0 2px rgba(248,239,223,.48)" : "none",
                transition: "width 220ms cubic-bezier(0.22,1,0.36,1), opacity var(--era-motion-fast)",
              }}
            />
          </button>
        );
      })}
    </nav>
  );
}
