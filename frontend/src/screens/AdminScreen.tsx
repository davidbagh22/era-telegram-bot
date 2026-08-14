import { useState } from "react";
import { ActionCell } from "../components/ActionCell";
import { AdminBottomNav, type AdminGroup } from "../components/AdminBottomNav";
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

type PeopleSection = "participants" | "applications" | "offices" | "data-rights";
type WorkSection = "projects" | "events" | "tasks" | "offers";
type CommsSection = "surveys" | "tools";

type SectionOption<T extends string> = { value: T; label: string; description: string };

const PEOPLE_SECTIONS: SectionOption<PeopleSection>[] = [
  { value: "participants", label: "Участники", description: "Люди, роли и состояние сообщества" },
  { value: "applications", label: "Заявки", description: "Новые регистрации и решения по ним" },
  { value: "offices", label: "Должности", description: "Организационные роли и структура" },
  { value: "data-rights", label: "Удаление данных", description: "Запросы по персональным данным" },
];

const WORK_SECTIONS: SectionOption<WorkSection>[] = [
  { value: "projects", label: "Проекты", description: "Модерация и состояние проектов" },
  { value: "events", label: "Мероприятия", description: "События, заявки и публикация" },
  { value: "tasks", label: "Задания", description: "Проверка результатов и начисления" },
  { value: "offers", label: "Возможности", description: "Партнёрские предложения и заявки" },
];

const COMMS_SECTIONS: SectionOption<CommsSection>[] = [
  { value: "surveys", label: "Опросы", description: "Обратная связь и активные опросы" },
  { value: "tools", label: "Инструменты", description: "Коммуникационные и служебные действия" },
];

function SectionMenu<T extends string>({
  title,
  description,
  options,
  onOpen,
}: {
  title: string;
  description: string;
  options: SectionOption<T>[];
  onOpen: (value: T) => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem", minWidth: 0 }}>
      <div>
        <p style={{ margin: "0 0 0.25rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
          Управление ЭРА
        </p>
        <h1 style={{ margin: 0, fontSize: "var(--era-text-3xl)" }}>{title}</h1>
        <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)" }}>{description}</p>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", minWidth: 0 }}>
        {options.map((option) => (
          <ActionCell
            key={option.value}
            title={option.label}
            description={option.description}
            onClick={() => onOpen(option.value)}
          />
        ))}
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

  const changeGroup = (next: AdminGroup) => {
    setGroup(next);
    setPeopleSection(null);
    setWorkSection(null);
    setCommsSection(null);
  };

  return (
    <div className="era-page" style={{ minHeight: "100vh", display: "flex", flexDirection: "column", minWidth: 0 }}>
      <div style={{ flex: "1 1 auto", minWidth: 0, padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        {group === "overview" && <AdminOverviewScreen />}

        {group === "people" && !peopleSection && (
          <SectionMenu
            title="Люди"
            description="Участники, регистрации, роли и права на данные."
            options={PEOPLE_SECTIONS}
            onOpen={setPeopleSection}
          />
        )}
        {group === "people" && peopleSection && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <SectionHeader title={PEOPLE_SECTIONS.find((item) => item.value === peopleSection)?.label ?? "Люди"} onBack={() => setPeopleSection(null)} />
            {peopleSection === "participants" && <AdminUsersScreen />}
            {peopleSection === "applications" && <AdminApplicationsScreen />}
            {peopleSection === "offices" && <AdminOfficesScreen />}
            {peopleSection === "data-rights" && <AdminDataRightsScreen />}
          </div>
        )}

        {group === "work" && !workSection && (
          <SectionMenu
            title="Работа"
            description="Проекты, мероприятия, задания и возможности."
            options={WORK_SECTIONS}
            onOpen={setWorkSection}
          />
        )}
        {group === "work" && workSection && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <SectionHeader title={WORK_SECTIONS.find((item) => item.value === workSection)?.label ?? "Работа"} onBack={() => setWorkSection(null)} />
            {workSection === "projects" && <AdminProjectsScreen />}
            {workSection === "events" && <AdminEventsScreen />}
            {workSection === "tasks" && <AdminTasksScreen />}
            {workSection === "offers" && <AdminOffersScreen />}
          </div>
        )}

        {group === "comms" && !commsSection && (
          <SectionMenu
            title="Коммуникации"
            description="Опросы и служебные инструменты связи."
            options={COMMS_SECTIONS}
            onOpen={setCommsSection}
          />
        )}
        {group === "comms" && commsSection && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <SectionHeader title={COMMS_SECTIONS.find((item) => item.value === commsSection)?.label ?? "Коммуникации"} onBack={() => setCommsSection(null)} />
            {commsSection === "surveys" && <AdminSurveysScreen />}
            {commsSection === "tools" && <AdminToolsScreen />}
          </div>
        )}
      </div>
      <AdminBottomNav active={group} onChange={changeGroup} />
    </div>
  );
}
