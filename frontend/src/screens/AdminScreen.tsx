import { useState } from "react";
import { PillTabs } from "../components/PillTabs";
import { AdminApplicationsScreen } from "./admin/AdminApplicationsScreen";
import { AdminDashboardScreen } from "./admin/AdminDashboardScreen";
import { AdminEventsScreen } from "./admin/AdminEventsScreen";
import { AdminOfficesScreen } from "./admin/AdminOfficesScreen";
import { AdminOffersScreen } from "./admin/AdminOffersScreen";
import { AdminProjectsScreen } from "./admin/AdminProjectsScreen";
import { AdminTasksScreen } from "./admin/AdminTasksScreen";
import { AdminUsersScreen } from "./admin/AdminUsersScreen";

type AdminSection =
  | "dashboard"
  | "applications"
  | "people"
  | "offices"
  | "projects"
  | "events"
  | "tasks"
  | "offers";

const SECTIONS: { value: AdminSection; label: string }[] = [
  { value: "dashboard", label: "Дашборд" },
  { value: "applications", label: "Заявки" },
  { value: "people", label: "Участники" },
  { value: "offices", label: "Должности" },
  { value: "projects", label: "Проекты" },
  { value: "events", label: "Мероприятия" },
  { value: "tasks", label: "Задания" },
  { value: "offers", label: "Возможности" },
];

export function AdminScreen() {
  const [section, setSection] = useState<AdminSection>("dashboard");

  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <PillTabs options={SECTIONS} active={section} onChange={setSection} />
      {section === "dashboard" && <AdminDashboardScreen />}
      {section === "applications" && <AdminApplicationsScreen />}
      {section === "people" && <AdminUsersScreen />}
      {section === "offices" && <AdminOfficesScreen />}
      {section === "projects" && <AdminProjectsScreen />}
      {section === "events" && <AdminEventsScreen />}
      {section === "tasks" && <AdminTasksScreen />}
      {section === "offers" && <AdminOffersScreen />}
    </div>
  );
}
