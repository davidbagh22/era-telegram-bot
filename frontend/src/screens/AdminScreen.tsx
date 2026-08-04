import { useState } from "react";
import { PillTabs } from "../components/PillTabs";
import { AdminApplicationsScreen } from "./admin/AdminApplicationsScreen";
import { AdminDashboardScreen } from "./admin/AdminDashboardScreen";
import { AdminEventsScreen } from "./admin/AdminEventsScreen";
import { AdminProjectsScreen } from "./admin/AdminProjectsScreen";

type AdminSection = "dashboard" | "applications" | "projects" | "events";

const SECTIONS: { value: AdminSection; label: string }[] = [
  { value: "dashboard", label: "Дашборд" },
  { value: "applications", label: "Заявки" },
  { value: "projects", label: "Проекты" },
  { value: "events", label: "Мероприятия" },
];

export function AdminScreen() {
  const [section, setSection] = useState<AdminSection>("dashboard");

  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <PillTabs options={SECTIONS} active={section} onChange={setSection} />
      {section === "dashboard" && <AdminDashboardScreen />}
      {section === "applications" && <AdminApplicationsScreen />}
      {section === "projects" && <AdminProjectsScreen />}
      {section === "events" && <AdminEventsScreen />}
    </div>
  );
}
