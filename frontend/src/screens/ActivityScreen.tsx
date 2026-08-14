import { useState } from "react";
import { Card } from "../components/Card";
import { CalendarIcon, EventIcon, HistoryIcon, ProjectsIcon, TaskIcon } from "../components/icons";
import { ProjectsSection } from "./projects/ProjectsSection";
import { CalendarTab } from "./activity/CalendarTab";
import { EventsTab } from "./activity/EventsTab";
import { HistoryTab } from "./activity/HistoryTab";
import { TasksTab } from "./activity/TasksTab";

type ActivitySection = "projects" | "events" | "tasks" | "calendar" | "history";

// 2026-08 redesign brief section 16: "Внутри Деятельности: Проекты,
// Задачи, Мероприятия, Календарь. Но не tabs. Четыре красивые action
// cards." "История" is a genuinely separate fifth area still worth its
// own place here (past events/tasks the four "active" areas above don't
// otherwise surface) -- kept rather than dropped outright, since the
// brief's own list wasn't meant as "delete this feature."
const SECTIONS: { value: ActivitySection; label: string; description: string; Icon: typeof ProjectsIcon }[] = [
  { value: "projects", label: "Проекты", description: "Свои инициативы и команды", Icon: ProjectsIcon },
  { value: "tasks", label: "Задачи", description: "Открытые и назначенные вам", Icon: TaskIcon },
  { value: "events", label: "Мероприятия", description: "Афиша и регистрация", Icon: EventIcon },
  { value: "calendar", label: "Календарь", description: "Всё, что впереди, по датам", Icon: CalendarIcon },
  { value: "history", label: "История", description: "Что вы уже прошли", Icon: HistoryIcon },
];

interface ActivityScreenProps {
  /** Lands the screen on a specific section instead of the landing menu —
   * used by the bot's "📅 Ближайшее"/"✅ Мои задачи" deep links (PR 36)
   * and by "#/projects/{id}" (App.tsx). */
  initialSection?: ActivitySection;
  /** A specific task/event id from a per-notification deep link
   * (`#/tasks/{id}`, `#/events/{id}`) — passed through to whichever
   * section `initialSection` lands on so it can scroll to and highlight
   * it. */
  initialItemId?: number | null;
  /** A specific project id from `#/projects/{id}` (App.tsx) — passed
   * through when `initialSection === "projects"`. */
  initialProjectId?: number | null;
}

export function ActivityScreen({ initialSection, initialItemId, initialProjectId }: ActivityScreenProps = {}) {
  const [section, setSection] = useState<ActivitySection | null>(initialSection ?? null);

  if (section === null) {
    return (
      <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "1.375rem", margin: 0 }}>
          Активность
        </h1>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {SECTIONS.map(({ value, label, description, Icon }) => (
            <Card key={value}>
              <button
                type="button"
                onClick={() => setSection(value)}
                style={{
                  all: "unset",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.875rem",
                  width: "100%",
                }}
              >
                <span
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: "2.75rem",
                    height: "2.75rem",
                    flexShrink: 0,
                    borderRadius: "var(--era-radius-control)",
                    background: "var(--era-gradient)",
                    color: "#fff",
                  }}
                  aria-hidden="true"
                >
                  <Icon />
                </span>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <strong style={{ display: "block", fontSize: "var(--era-text-lg)" }}>{label}</strong>
                  <span style={{ display: "block", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
                    {description}
                  </span>
                </span>
                <span aria-hidden="true" style={{ color: "var(--era-text-muted)" }}>
                  →
                </span>
              </button>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  const current = SECTIONS.find((item) => item.value === section);

  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <button type="button" onClick={() => setSection(null)}>
        ← Деятельность
      </button>
      <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "1.375rem", margin: 0 }}>
        {current?.label}
      </h1>
      {section === "projects" && <ProjectsSection initialProjectId={initialProjectId} />}
      {section === "tasks" && <TasksTab initialItemId={section === initialSection ? initialItemId ?? null : null} />}
      {section === "events" && <EventsTab initialItemId={section === initialSection ? initialItemId ?? null : null} />}
      {section === "calendar" && <CalendarTab />}
      {section === "history" && <HistoryTab />}
    </div>
  );
}
