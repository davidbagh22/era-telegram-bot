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

export function ActivityScreen() {
  const [section, setSection] = useState<ActivitySection>("events");

  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "1.375rem", margin: 0 }}>
        Активность
      </h1>
      <PillTabs options={SECTIONS} active={section} onChange={setSection} />
      {section === "events" && <EventsTab />}
      {section === "tasks" && <TasksTab />}
      {section === "calendar" && <CalendarTab />}
      {section === "history" && <HistoryTab />}
    </div>
  );
}
