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
  { key: "projects", label: "Проекты", Icon: ProjectsIcon },
  { key: "events", label: "События", Icon: EventIcon },
  // Keep the internal `community` key for backwards-compatible deep links,
  // but the primary participant navigation is the approved Opportunities
  // surface. Secondary community tools remain reachable through their own
  // deep links and screens; they are not a sixth main tab.
  { key: "community", label: "Возможности", Icon: OpportunitiesIcon },
  { key: "profile", label: "Профиль", Icon: ProfileIcon },
];

interface FloatingNavProps {
  active: TabKey;
  onChange: (tab: TabKey) => void;
}

/** Floating white/glass bottom nav: five primary participant destinations. */
export function FloatingNav({ active, onChange }: FloatingNavProps) {
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
        backdropFilter: "blur(26px) saturate(140%)",
        WebkitBackdropFilter: "blur(26px) saturate(140%)",
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
          background: "linear-gradient(180deg, rgba(99,44,255,.14), rgba(99,44,255,.06))",
          border: "1px solid rgba(99,44,255,.16)",
          boxShadow: "inset 0 1px 0 rgba(255,255,255,.6), 0 0 22px rgba(99,44,255,.16)",
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
              if (key === "community") {
                if (window.location.hash !== "#/opportunities") {
                  window.location.hash = "#/opportunities";
                }
                return;
              }
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
              color: isActive ? "var(--era-violet)" : "var(--era-nav-muted, var(--era-text-muted))",
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
                bottom: 3,
                width: isActive ? 5 : 0,
                height: 5,
                borderRadius: 999,
                background: "var(--era-gradient-signal)",
                opacity: isActive ? 1 : 0,
                transform: "translateX(-50%)",
                boxShadow: isActive ? "0 0 8px rgba(99,44,255,.55)" : "none",
                transition: "width 220ms cubic-bezier(0.22,1,0.36,1), opacity var(--era-motion-fast)",
              }}
            />
          </button>
        );
      })}
    </nav>
  );
}
