import {
  EventIcon,
  OrbitIcon,
  OpportunitiesIcon,
  ProfileIcon,
  ProjectsIcon,
} from "./icons";
import { selectionHaptic } from "../telegram/webApp";

export type TabKey = "home" | "projects" | "events" | "community" | "profile";

const TABS: { key: TabKey; label: string; Icon: typeof OrbitIcon }[] = [
  { key: "home", label: "Орбита", Icon: OrbitIcon },
  { key: "events", label: "Афиша", Icon: EventIcon },
  { key: "projects", label: "Проекты", Icon: ProjectsIcon },
  { key: "community", label: "Открытия", Icon: OpportunitiesIcon },
  { key: "profile", label: "Я", Icon: ProfileIcon },
];

interface FloatingNavProps {
  active: TabKey;
  onChange: (tab: TabKey) => void;
}

/** Five primary participant destinations (AURA×ORBIT D08). */
export function FloatingNav({ active, onChange }: FloatingNavProps) {
  return (
    <nav
      aria-label="Основная навигация"
      className="era-bottom-nav"
      data-active-tab={active}
      style={{
        position: "fixed",
        left: "50%",
        bottom: "calc(0.55rem + var(--era-safe-bottom))",
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
              background: isActive ? "var(--era-selected)" : "transparent",
              border: "none",
              boxShadow: "none",
              color: isActive ? "var(--era-cyan)" : "var(--era-nav-muted, var(--era-text-muted))",
              fontSize: "0.7rem",
              fontWeight: isActive ? 800 : 650,
              padding: "0.38rem 0.05rem",
              borderRadius: "1.1rem",
              transition: "color var(--era-motion-fast), background var(--era-motion-fast)",
            }}
          >
            <span aria-hidden="true" style={{ display: "grid", placeItems: "center", width: 32, height: 26 }}>
              <Icon width={21} height={21} />
            </span>
            <span style={{ maxWidth: "100%", lineHeight: 1.1, textAlign: "center", whiteSpace: "nowrap" }}>
              {label}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
