import {
  EventIcon,
  HomeIcon,
  OpportunitiesIcon,
  ProfileIcon,
  ProjectsIcon,
} from "./icons";
import { selectionHaptic } from "../telegram/webApp";

export type TabKey = "home" | "projects" | "events" | "community" | "profile";

const TABS: { key: TabKey; label: string; Icon: typeof HomeIcon }[] = [
  { key: "home", label: "Главная", Icon: HomeIcon },
  { key: "events", label: "Участие", Icon: EventIcon },
  { key: "projects", label: "Проекты", Icon: ProjectsIcon },
  { key: "community", label: "Возможности", Icon: OpportunitiesIcon },
  { key: "profile", label: "Профиль", Icon: ProfileIcon },
];

interface FloatingNavProps {
  active: TabKey;
  onChange: (tab: TabKey) => void;
}

/** Five primary participant destinations. Active state stays quiet and clear. */
export function FloatingNav({ active, onChange }: FloatingNavProps) {
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
        backdropFilter: "blur(22px) saturate(130%)",
        WebkitBackdropFilter: "blur(22px) saturate(130%)",
        overflow: "hidden",
        zIndex: 32,
      }}
    >
      {TABS.map(({ key, label, Icon }) => {
        const isActive = key === active;
        return (
          <button
            key={key}
            type="button"
            onClick={() => {
              if (!isActive) selectionHaptic();
              if (key === "community") {
                if (window.location.hash !== "#/opportunities") window.location.hash = "#/opportunities";
                return;
              }
              onChange(key);
            }}
            aria-current={isActive ? "page" : undefined}
            aria-label={label}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: "0.15rem",
              minHeight: 52,
              minWidth: 0,
              background: isActive ? "rgba(99,44,255,.10)" : "transparent",
              border: "none",
              boxShadow: "none",
              color: isActive ? "var(--era-violet)" : "var(--era-nav-muted, var(--era-text-muted))",
              fontSize: "0.75rem",
              fontWeight: isActive ? 800 : 650,
              padding: "0.38rem 0.1rem",
              borderRadius: "1.1rem",
              transition: "color var(--era-motion-fast), background var(--era-motion-fast)",
            }}
          >
            <span aria-hidden="true" style={{ display: "grid", placeItems: "center", width: 32, height: 26 }}>
              <Icon width={21} height={21} />
            </span>
            <span style={{ maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {label}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
