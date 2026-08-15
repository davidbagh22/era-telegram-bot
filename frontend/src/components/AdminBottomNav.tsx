import { AnalyticsIcon, CommsIcon, OverviewIcon, PeopleIcon, WorkIcon } from "./icons";

export type AdminGroup = "overview" | "people" | "work" | "comms" | "control";

const GROUPS: { key: AdminGroup; label: string; Icon: typeof OverviewIcon }[] = [
  { key: "overview", label: "Обзор", Icon: OverviewIcon },
  { key: "people", label: "Люди", Icon: PeopleIcon },
  { key: "work", label: "Работа", Icon: WorkIcon },
  { key: "comms", label: "Связь", Icon: CommsIcon },
  { key: "control", label: "Контроль", Icon: AnalyticsIcon },
];

interface AdminBottomNavProps {
  active: AdminGroup;
  onChange: (group: AdminGroup) => void;
}

export function AdminBottomNav({ active, onChange }: AdminBottomNavProps) {
  return (
    <nav
      aria-label="Разделы управления ЭРА"
      style={{
        position: "sticky",
        bottom: 0,
        display: "flex",
        minWidth: 0,
        gap: "0.125rem",
        margin: "0 0.5rem calc(0.6rem + env(safe-area-inset-bottom, 0px))",
        padding: "0.35rem",
        background: "linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.012)), var(--era-surface)",
        border: "1px solid var(--era-border)",
        borderRadius: "var(--era-radius-pill)",
        boxShadow: "var(--era-shadow-dock)",
        backdropFilter: "blur(22px)",
        WebkitBackdropFilter: "blur(22px)",
      }}
    >
      {GROUPS.map(({ key, label, Icon }) => {
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
              minHeight: "44px",
              flex: "1 1 0",
              minWidth: 0,
              background: "none",
              border: "none",
              color: isActive ? "#fff" : "var(--era-text-muted)",
              fontFamily: "var(--era-font-body)",
              fontSize: "0.625rem",
              fontWeight: isActive ? 700 : 500,
              padding: "0.45rem 0.1rem",
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
                  background: "linear-gradient(135deg, var(--era-red), var(--era-magenta))",
                  boxShadow: "0 9px 22px rgba(255, 32, 56, 0.36)",
                  zIndex: -1,
                }}
              />
            )}
            <Icon width={21} height={21} />
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