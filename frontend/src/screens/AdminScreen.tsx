import { useState } from "react";
import { AdminBottomNav, type AdminGroup } from "../components/AdminBottomNav";
import { FilterChips } from "../components/FilterChips";
import { AdminApplicationsScreen } from "./admin/AdminApplicationsScreen";
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

// 2026-08 Admin Mode redesign, round 2: the old flat 12-tab PillTabs row
// was replaced (see git history) by logical groups reached through a
// SegmentedTabs row at the top — itself now replaced by a fixed bottom
// dock (AdminBottomNav), the master spec's explicit "not a long segmented
// control" requirement for Admin Mode's top-level navigation. Same
// screens underneath, same sub-navigation approach where a group has more
// than one screen ("не пытаться одновременно показать всё") — this pass
// only moves the group switcher itself from a scrollable top row to a
// fixed dock, matching the same floating-dock pattern already used for
// the participant-facing bottom nav. See docs/UI_DESIGN_SYSTEM.md for the
// grouping rationale and AdminOverviewScreen for what replaced the old
// dashboard-as-landing-screen.
//
// Round 3 (redesign brief section 34, "4 фиксированные группы"): the
// standalone Аналитика group is gone — AdminDashboardScreen now lives
// inside AdminOverviewScreen as a collapsible section instead of its own
// bottom-nav destination.
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
    <div
      className="era-page"
      style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}
    >
      <div style={{ flex: "1 1 auto", minWidth: 0, padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        {group === "overview" && <AdminOverviewScreen />}

        {group === "people" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <FilterChips options={PEOPLE_SECTIONS} active={peopleSection} onChange={setPeopleSection} />
            {peopleSection === "participants" && <AdminUsersScreen />}
            {peopleSection === "applications" && <AdminApplicationsScreen />}
            {peopleSection === "offices" && <AdminOfficesScreen />}
            {peopleSection === "data-rights" && <AdminDataRightsScreen />}
          </div>
        )}

        {group === "work" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <FilterChips options={WORK_SECTIONS} active={workSection} onChange={setWorkSection} />
            {workSection === "projects" && <AdminProjectsScreen />}
            {workSection === "events" && <AdminEventsScreen />}
            {workSection === "tasks" && <AdminTasksScreen />}
            {workSection === "offers" && <AdminOffersScreen />}
          </div>
        )}

        {group === "comms" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <FilterChips options={COMMS_SECTIONS} active={commsSection} onChange={setCommsSection} />
            {commsSection === "surveys" && <AdminSurveysScreen />}
            {commsSection === "tools" && <AdminToolsScreen />}
          </div>
        )}
      </div>
      <AdminBottomNav active={group} onChange={setGroup} />
    </div>
  );
}
