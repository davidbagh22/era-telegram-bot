import { useState } from "react";
import { ProjectsSection } from "./projects/ProjectsSection";
import { CalendarTab } from "./activity/CalendarTab";
import { EventsTab } from "./activity/EventsTab";
import { HistoryTab } from "./activity/HistoryTab";
import { TasksTab } from "./activity/TasksTab";

type ActivitySection = "now" | "projects" | "events" | "tasks" | "calendar" | "history";
type VisibleSection = "now" | "events" | "tasks" | "history";

const TABS: { value: VisibleSection; label: string }[] = [
  { value: "now", label: "Сейчас" },
  { value: "events", label: "События" },
  { value: "tasks", label: "Задачи" },
  { value: "history", label: "История" },
];

interface ActivityScreenProps {
  initialSection?: ActivitySection;
  initialItemId?: number | null;
  initialProjectId?: number | null;
}

function visibleInitial(section?: ActivitySection): VisibleSection | "projects" {
  if (section === "projects") return "projects";
  if (section === "events" || section === "tasks" || section === "history") return section;
  return "now";
}

export function ActivityScreen({ initialSection, initialItemId, initialProjectId }: ActivityScreenProps = {}) {
  const [section, setSection] = useState<VisibleSection | "projects">(() => visibleInitial(initialSection));

  if (section === "projects") {
    return (
      <div className="era-page" style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <button type="button" onClick={() => setSection("now")} style={{ alignSelf: "flex-start", minHeight: 44 }}>← Участие</button>
        <ProjectsSection initialProjectId={initialProjectId} />
      </div>
    );
  }

  return (
    <div className="era-page" style={{ padding: "1rem 1rem var(--era-page-bottom-safe)", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <header>
        <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "1.8rem", lineHeight: 1.08, margin: 0 }}>Участие</h1>
        <p style={{ margin: ".35rem 0 0", color: "var(--era-text-secondary)", fontSize: ".9rem", lineHeight: 1.45 }}>
          Всё, где ты сейчас включён: события, задачи и подтверждённый результат.
        </p>
      </header>

      <div
        role="tablist"
        aria-label="Разделы участия"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
          gap: ".35rem",
          padding: ".3rem",
          borderRadius: "var(--era-radius-pill)",
          background: "var(--era-surface-2)",
          border: "1px solid var(--era-border)",
        }}
      >
        {TABS.map((tab) => {
          const active = tab.value === section;
          return (
            <button
              key={tab.value}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setSection(tab.value)}
              style={{
                minHeight: 44,
                padding: ".5rem .25rem",
                border: 0,
                borderRadius: "var(--era-radius-pill)",
                background: active ? "rgba(99,44,255,.10)" : "transparent",
                color: active ? "var(--era-violet)" : "var(--era-text-secondary)",
                fontSize: ".75rem",
                fontWeight: active ? 800 : 650,
                boxShadow: "none",
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      <div role="tabpanel">
        {section === "now" && <CalendarTab />}
        {section === "tasks" && <TasksTab initialItemId={initialSection === "tasks" ? initialItemId ?? null : null} />}
        {section === "events" && <EventsTab initialItemId={initialSection === "events" ? initialItemId ?? null : null} />}
        {section === "history" && <HistoryTab />}
      </div>
    </div>
  );
}
