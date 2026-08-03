import { useState } from "react";
import { PillTabs } from "../components/PillTabs";
import { OpenTasksTab } from "./leader/OpenTasksTab";
import { OverviewTab } from "./leader/OverviewTab";

type LeaderSection = "overview" | "open-tasks";

const SECTIONS: { value: LeaderSection; label: string }[] = [
  { value: "overview", label: "Обзор" },
  { value: "open-tasks", label: "Открытые задачи" },
];

export function LeaderScreen() {
  const [section, setSection] = useState<LeaderSection>("overview");

  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "1.375rem", margin: 0 }}>
        Панель лидера
      </h1>
      <PillTabs options={SECTIONS} active={section} onChange={setSection} />
      {section === "overview" && <OverviewTab />}
      {section === "open-tasks" && <OpenTasksTab />}
    </div>
  );
}
