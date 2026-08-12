import { useState } from "react";
import { PillTabs } from "../components/PillTabs";
import { CalendarTab } from "./activity/CalendarTab";
import { EventsTab } from "./activity/EventsTab";
import { HistoryTab } from "./activity/HistoryTab";
import { TasksTab } from "./activity/TasksTab";

type ActivitySection = "events" | "tasks" | "calendar" | "history";

const SECTIONS: { value: ActivitySection; label: string }[] = [
  { value: "events", label: "События" },
  { value: "tasks", label: "Задачи" },
  { value: "calendar", label: "Календарь" },
  { value: "history", label: "История" },
];

interface ActivityScreenProps {
  /** Lands the screen on a specific tab instead of the "events" default —
   * used by the bot's "📅 Ближайшее"/"✅ Мои задачи" deep links (PR 36). */
  initialSection?: ActivitySection;
  /** A specific task/event id from a per-notification deep link
   * (`#/tasks/{id}`, `#/events/{id}`) — passed through to whichever tab
   * `initialSection` lands on so it can scroll to and highlight it. */
  initialItemId?: number | null;
}

export function ActivityScreen({ initialSection, initialItemId }: ActivityScreenProps = {}) {
  const [section, setSection] = useState<ActivitySection>(initialSection ?? "events");

  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "1.375rem", margin: 0 }}>
        Активность
      </h1>
      <PillTabs options={SECTIONS} active={section} onChange={setSection} />
      {section === "events" && <EventsTab initialItemId={section === initialSection ? initialItemId : null} />}
      {section === "tasks" && <TasksTab initialItemId={section === initialSection ? initialItemId : null} />}
      {section === "calendar" && <CalendarTab />}
      {section === "history" && <HistoryTab />}
    </div>
  );
}
