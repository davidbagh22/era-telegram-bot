import { useState } from "react";
import { ActionCell } from "../components/ActionCell";
import { AdminBottomNav, type AdminGroup } from "../components/AdminBottomNav";
import { AdminApplicationsScreen } from "./admin/AdminApplicationsScreen";
import { AdminDashboardScreen } from "./admin/AdminDashboardScreen";
import { AdminDataRightsScreen } from "./admin/AdminDataRightsScreen";
import { AdminEventsScreen } from "./admin/AdminEventsScreen";
import { AdminMaintenanceScreen } from "./admin/AdminMaintenanceScreen";
import { AdminOfficesScreen } from "./admin/AdminOfficesScreen";
import { AdminOffersScreen } from "./admin/AdminOffersScreen";
import { AdminOverviewScreen } from "./admin/AdminOverviewScreen";
import { AdminProjectsScreen } from "./admin/AdminProjectsScreen";
import { AdminSurveysScreen } from "./admin/AdminSurveysScreen";
import { AdminTasksScreen } from "./admin/AdminTasksScreen";
import { AdminToolsScreen, type ToolsSection } from "./admin/AdminToolsScreen";
import { AdminUsersScreen } from "./admin/AdminUsersScreen";
import { SystemPanel } from "./admin/tools/SystemPanel";

type PeopleSection = "participants" | "applications" | "offices" | "data-rights";
type WorkSection = "projects" | "events" | "tasks" | "offers";
type CommsSection = "surveys" | "tools";
type ControlSection = "analytics" | "system" | "maintenance";

type SectionOption<T extends string> = { value: T; label: string; description: string };

const PEOPLE_SECTIONS: SectionOption<PeopleSection>[] = [
  { value: "participants", label: "Участники", description: "Люди, роли и состояние сообщества" },
  { value: "applications", label: "Заявки", description: "Новые регистрации и решения по ним" },
  { value: "offices", label: "Должности", description: "Организационные роли и структура" },
  { value: "data-rights", label: "Данные и права", description: "Запросы на экспорт и удаление персональных данных" },
];

const WORK_SECTIONS: SectionOption<WorkSection>[] = [
  { value: "projects", label: "Проекты", description: "Создание, модерация и команды проектов" },
  { value: "events", label: "Мероприятия", description: "Создание, публикация, участники и активности" },
  { value: "tasks", label: "Задания", description: "Создание задач и проверка результатов" },
  { value: "offers", label: "Возможности", description: "Партнёрские предложения и заявки" },
];

const COMMS_SECTIONS: SectionOption<CommsSection>[] = [
  { value: "surveys", label: "Опросы", description: "Обратная связь и активные опросы" },
  { value: "tools", label: "Центр связи", description: "Чаты, FAQ, приветствия, рассылки и автоконтент" },
];

const CONTROL_SECTIONS: SectionOption<ControlSection>[] = [
  { value: "analytics", label: "ЭРА сейчас", description: "Живые показатели с переходом к реальным данным" },
  { value: "system", label: "Состояние системы", description: "Диагностика, инциденты, резервные копии и здоровье ЭРА" },
  { value: "maintenance", label: "Обслуживание", description: "Редкие технические операции с отдельной серверной защитой" },
];

function SectionMenu<T extends string>({ title, description, options, onOpen }: { title: string; description: string; options: SectionOption<T>[]; onOpen: (value: T) => void }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem", minWidth: 0 }}>
      <div>
        <p style={{ margin: "0 0 0.25rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Управление ЭРА</p>
        <h1 style={{ margin: 0, fontSize: "var(--era-text-3xl)" }}>{title}</h1>
        <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)" }}>{description}</p>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", minWidth: 0 }}>
        {options.map((option) => <ActionCell key={option.value} title={option.label} description={option.description} onClick={() => onOpen(option.value)} />)}
      </div>
    </div>
  );
}

function SectionHeader({ title, onBack }: { title: string; onBack: () => void }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← Назад</button>
      <h1 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>{title}</h1>
    </div>
  );
}

export function AdminScreen() {
  const [group, setGroup] = useState<AdminGroup>("overview");
  const [peopleSection, setPeopleSection] = useState<PeopleSection | null>(null);
  const [workSection, setWorkSection] = useState<WorkSection | null>(null);
  const [commsSection, setCommsSection] = useState<CommsSection | null>(null);
  const [controlSection, setControlSection] = useState<ControlSection | null>(null);
  const [toolsInitialSection, setToolsInitialSection] = useState<ToolsSection | null>(null);

  const clearSections = () => {
    setPeopleSection(null);
    setWorkSection(null);
    setCommsSection(null);
    setControlSection(null);
    setToolsInitialSection(null);
  };

  const changeGroup = (next: AdminGroup) => {
    setGroup(next);
    clearSections();
  };

  const openPeople = (section: PeopleSection) => {
    setGroup("people");
    setPeopleSection(section);
    setWorkSection(null);
    setCommsSection(null);
    setControlSection(null);
    setToolsInitialSection(null);
  };

  const openWork = (section: WorkSection) => {
    setGroup("work");
    setWorkSection(section);
    setPeopleSection(null);
    setCommsSection(null);
    setControlSection(null);
    setToolsInitialSection(null);
  };

  const openComms = () => {
    setGroup("comms");
    setCommsSection("tools");
    setToolsInitialSection(null);
    setPeopleSection(null);
    setWorkSection(null);
    setControlSection(null);
  };

  const openTool = (section: ToolsSection) => {
    setGroup("comms");
    setCommsSection("tools");
    setToolsInitialSection(section);
    setPeopleSection(null);
    setWorkSection(null);
    setControlSection(null);
  };

  return (
    <div className="era-page" style={{ minHeight: "100vh", display: "flex", flexDirection: "column", minWidth: 0 }}>
      <div style={{ flex: "1 1 auto", minWidth: 0, padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        {group === "overview" && (
          <AdminOverviewScreen
            onOpenApplications={() => openPeople("applications")}
            onOpenProjects={() => openWork("projects")}
            onOpenEvents={() => openWork("events")}
            onOpenComms={openComms}
          />
        )}

        {group === "people" && !peopleSection && <SectionMenu title="Люди" description="Участники, регистрации, роли и права на данные." options={PEOPLE_SECTIONS} onOpen={setPeopleSection} />}
        {group === "people" && peopleSection && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <SectionHeader title={PEOPLE_SECTIONS.find((item) => item.value === peopleSection)?.label ?? "Люди"} onBack={() => setPeopleSection(null)} />
            {peopleSection === "participants" && <AdminUsersScreen />}
            {peopleSection === "applications" && <AdminApplicationsScreen />}
            {peopleSection === "offices" && <AdminOfficesScreen />}
            {peopleSection === "data-rights" && <AdminDataRightsScreen />}
          </div>
        )}

        {group === "work" && !workSection && <SectionMenu title="Работа" description="Создание и управление проектами, мероприятиями, заданиями и возможностями." options={WORK_SECTIONS} onOpen={setWorkSection} />}
        {group === "work" && workSection && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <SectionHeader title={WORK_SECTIONS.find((item) => item.value === workSection)?.label ?? "Работа"} onBack={() => setWorkSection(null)} />
            {workSection === "projects" && <AdminProjectsScreen />}
            {workSection === "events" && <AdminEventsScreen />}
            {workSection === "tasks" && <AdminTasksScreen />}
            {workSection === "offers" && <AdminOffersScreen />}
          </div>
        )}

        {group === "comms" && !commsSection && <SectionMenu title="Связь" description="Чаты, рассылки и обратная связь без системных функций." options={COMMS_SECTIONS} onOpen={(next) => { setToolsInitialSection(null); setCommsSection(next); }} />}
        {group === "comms" && commsSection && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <SectionHeader title={COMMS_SECTIONS.find((item) => item.value === commsSection)?.label ?? "Связь"} onBack={() => { setCommsSection(null); setToolsInitialSection(null); }} />
            {commsSection === "surveys" && <AdminSurveysScreen />}
            {commsSection === "tools" && <AdminToolsScreen initialSection={toolsInitialSection} />}
          </div>
        )}

        {group === "control" && !controlSection && <SectionMenu title="Контроль" description="Живые данные ЭРА, здоровье платформы и техническое обслуживание." options={CONTROL_SECTIONS} onOpen={setControlSection} />}
        {group === "control" && controlSection && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <SectionHeader title={CONTROL_SECTIONS.find((item) => item.value === controlSection)?.label ?? "Контроль"} onBack={() => setControlSection(null)} />
            {controlSection === "analytics" && (
              <AdminDashboardScreen
                onOpenParticipants={() => openPeople("participants")}
                onOpenProjects={() => openWork("projects")}
                onOpenEvents={() => openWork("events")}
                onOpenOrganizations={() => openTool("contacts")}
                onOpenGoals={() => openTool("goals")}
                onOpenApplications={() => openPeople("applications")}
                onOpenTasks={() => openWork("tasks")}
                onOpenOffers={() => openWork("offers")}
              />
            )}
            {controlSection === "system" && <SystemPanel />}
            {controlSection === "maintenance" && <AdminMaintenanceScreen />}
          </div>
        )}
      </div>
      <AdminBottomNav active={group} onChange={changeGroup} />
    </div>
  );
}
