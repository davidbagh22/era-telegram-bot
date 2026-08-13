import { useState } from "react";
import { PillTabs } from "../components/PillTabs";
import { AdminApplicationsScreen } from "./admin/AdminApplicationsScreen";
import { AdminDashboardScreen } from "./admin/AdminDashboardScreen";
import { AdminDataRightsScreen } from "./admin/AdminDataRightsScreen";
import { AdminEventsScreen } from "./admin/AdminEventsScreen";
import { AdminOfficesScreen } from "./admin/AdminOfficesScreen";
import { AdminOffersScreen } from "./admin/AdminOffersScreen";
import { AdminOverviewScreen } from "./admin/AdminOverviewScreen";
import { AdminProjectsScreen } from "./admin/AdminProjectsScreen";
import { AdminSurveysScreen } from "./admin/AdminSurveysScreen";
import { AdminTasksScreen } from "./admin/AdminTasksScreen";
import { AdminToolsScreen } from "./admin/AdminToolsScreen";
import { AdminUsersScreen } from "./admin/AdminUsersScreen";

// 2026-08 Admin Mode redesign: the old flat 12-tab PillTabs row
// (Дашборд/Заявки/Участники/Должности/Проекты/Мероприятия/Задания/
// Возможности/Опросы/Инструменты/Удаление данных/Обслуживание, all in
// one horizontal scroller) is replaced by 5 logical groups, each with
// its own sub-navigation where it actually has more than one screen —
// "не пытаться одновременно показать всё" (don't try to show everything
// at once). No screen listed below was rewritten as part of this
// change — this only regroups how they're reached. See
// docs/UI_DESIGN_SYSTEM.md for the full rationale and AdminOverviewScreen
// for what replaced the old dashboard-as-landing-screen.
type AdminGroup = "overview" | "people" | "work" | "comms" | "analytics";

const GROUPS: { value: AdminGroup; label: string }[] = [
  { value: "overview", label: "Обзор" },
  { value: "people", label: "Люди" },
  { value: "work", label: "Работа" },
  { value: "comms", label: "Коммуникации" },
  { value: "analytics", label: "Аналитика" },
];

type PeopleSection = "participants" | "applications" | "offices" | "data-rights";

const PEOPLE_SECTIONS: { value: PeopleSection; label: string }[] = [
  { value: "participants", label: "Участники" },
  { value: "applications", label: "Заявки" },
  { value: "offices", label: "Должности" },
  { value: "data-rights", label: "Удаление данных" },
];

type WorkSection = "projects" | "events" | "tasks" | "offers";

const WORK_SECTIONS: { value: WorkSection; label: string }[] = [
  { value: "projects", label: "Проекты" },
  { value: "events", label: "Мероприятия" },
  { value: "tasks", label: "Задания" },
  { value: "offers", label: "Возможности" },
];

type CommsSection = "surveys" | "tools";

const COMMS_SECTIONS: { value: CommsSection; label: string }[] = [
  { value: "surveys", label: "Опросы" },
  { value: "tools", label: "Инструменты" },
];

export function AdminScreen() {
  const [group, setGroup] = useState<AdminGroup>("overview");
  const [peopleSection, setPeopleSection] = useState<PeopleSection>("participants");
  const [workSection, setWorkSection] = useState<WorkSection>("projects");
  const [commsSection, setCommsSection] = useState<CommsSection>("surveys");

  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <PillTabs options={GROUPS} active={group} onChange={setGroup} />

      {group === "overview" && <AdminOverviewScreen />}

      {group === "people" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <PillTabs options={PEOPLE_SECTIONS} active={peopleSection} onChange={setPeopleSection} />
          {peopleSection === "participants" && <AdminUsersScreen />}
          {peopleSection === "applications" && <AdminApplicationsScreen />}
          {peopleSection === "offices" && <AdminOfficesScreen />}
          {peopleSection === "data-rights" && <AdminDataRightsScreen />}
        </div>
      )}

      {group === "work" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <PillTabs options={WORK_SECTIONS} active={workSection} onChange={setWorkSection} />
          {workSection === "projects" && <AdminProjectsScreen />}
          {workSection === "events" && <AdminEventsScreen />}
          {workSection === "tasks" && <AdminTasksScreen />}
          {workSection === "offers" && <AdminOffersScreen />}
        </div>
      )}

      {group === "comms" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <PillTabs options={COMMS_SECTIONS} active={commsSection} onChange={setCommsSection} />
          {commsSection === "surveys" && <AdminSurveysScreen />}
          {commsSection === "tools" && <AdminToolsScreen />}
        </div>
      )}

      {group === "analytics" && <AdminDashboardScreen />}
    </div>
  );
}
