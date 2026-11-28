import { useState } from "react";
import { AdminWorkcenterScreen } from "./admin/AdminWorkcenterScreen";
import { ActionCell } from "../components/ActionCell";
import { AdminBottomNav, type AdminGroup } from "../components/AdminBottomNav";
import type { AdminMetricKey } from "../types/adminMetrics";
import { AdminApplicationsScreen } from "./admin/AdminApplicationsScreen";
import { AdminCareerScreen } from "./admin/AdminCareerScreen";
import { AdminDataRightsScreen } from "./admin/AdminDataRightsScreen";
import { AdminDevelopmentScreen } from "./admin/AdminDevelopmentScreen";
import { AdminEventsScreen } from "./admin/AdminEventsScreen";
import { AdminMetricDetailScreen } from "./admin/AdminMetricDetailScreen";
import { AdminAppointLeaderScreen } from "./admin/AdminAppointLeaderScreen";
import { AdminOfficesScreen } from "./admin/AdminOfficesScreen";
import { AdminOffersScreen, type OffersSection } from "./admin/AdminOffersScreen";
import { AdminAttendanceProofsScreen } from "./admin/AdminAttendanceProofsScreen";
import { AdminOverviewScreen } from "./admin/AdminOverviewScreen";
import { AdminProjectsScreen } from "./admin/AdminProjectsScreen";
import { AdminSurveysScreen } from "./admin/AdminSurveysScreen";
import { AdminTasksScreen, type TasksSection } from "./admin/AdminTasksScreen";
import { AdminToolsScreen, type ToolsSection } from "./admin/AdminToolsScreen";
import { AdminUsersScreen } from "./admin/AdminUsersScreen";
import { AdminVerificationScreen } from "./admin/AdminVerificationScreen";

type PeopleSection = "participants" | "verification" | "development" | "career" | "applications" | "leaders-chat" | "appoint-leader" | "offices" | "data-rights";
type WorkSection = "pulse" | "projects" | "events" | "tasks" | "offers";
type CommsSection = "surveys" | "tools";
type EventsLaunch = { section: "moderation" | "activities" | "operations" | "create"; activitiesMode?: "review" | "manage" };
type ProjectsLaunch = { section: "create" | "moderation" | "team-posts" };
type TasksLaunch = { section: TasksSection; openCreate?: boolean };
type ToolsLaunch = { section: ToolsSection };
type SectionOption<T extends string> = { value: T; label: string; description: string };
type MetricDetail = { metric: AdminMetricKey; total: number };

type InitialAdminRoute = {
  peopleSection: PeopleSection | null;
  workSection: WorkSection | null;
  commsSection: CommsSection | null;
  toolsLaunch: ToolsLaunch | null;
  tasksLaunch: TasksLaunch | null;
  eventsLaunch: EventsLaunch | null;
  overviewView: "home" | "decisions";
  applicationId: number | null;
};

const PEOPLE_SECTIONS: SectionOption<PeopleSection>[] = [
  { value: "participants", label: "Участники", description: "Люди, роли и состояние сообщества" },
  { value: "verification", label: "Проверка состава", description: "Проверка состава, напоминания и ручные решения" },
  { value: "development", label: "Состояние и развитие", description: "Добровольные ежемесячные отметки, охват и потребности сообщества" },
  { value: "career", label: "Портфолио и рекомендации", description: "Проверка достижений и утверждение официальных рекомендательных писем" },
  { value: "applications", label: "Заявки", description: "Новые регистрации и решения по ним" },
  { value: "leaders-chat", label: "Лидеры", description: "Команда, задачи, рассылки и Пульс" },
  { value: "appoint-leader", label: "Назначить руководителя", description: "Человек → пакеты функций → права открываются сразу" },
  { value: "offices", label: "Должности", description: "Роли, набор, заявки, назначения и ответственность" },
  { value: "data-rights", label: "Данные и права", description: "Запросы на удаление персональных данных" },
];

const WORK_SECTIONS: SectionOption<WorkSection>[] = [
  { value: "projects", label: "Проекты", description: "Создание, модерация и команды проектов" },
  { value: "events", label: "Мероприятия", description: "Создание, публикация, участники и активности" },
  { value: "tasks", label: "Задания", description: "Создание задач и проверка результатов" },
  { value: "offers", label: "Возможности", description: "Партнёрские предложения и заявки" },
];

const COMMS_SECTIONS: SectionOption<CommsSection>[] = [
  { value: "surveys", label: "Опросы", description: "Обратная связь и активные опросы" },
  { value: "tools", label: "Центр связи", description: "Чаты, вопросы и ответы, приветствия, рассылки и автоконтент" },
];

function positiveId(value: string | null): number | null {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function initialAdminRoute(): InitialAdminRoute {
  const query = new URLSearchParams(window.location.search);
  const section = query.get("adminSection");
  const base: InitialAdminRoute = {
    peopleSection: null,
    workSection: null,
    commsSection: null,
    toolsLaunch: null,
    tasksLaunch: null,
    eventsLaunch: null,
    overviewView: "home",
    applicationId: null,
  };
  const people = (peopleSection: PeopleSection, applicationId: number | null = null): InitialAdminRoute => ({
    ...base,
    peopleSection,
    applicationId,
  });
  if (section === "applications") return people("applications", positiveId(query.get("applicationId")));
  if (section === "team-tasks") return people("leaders-chat");
  if (section === "offices") return people("offices");
  if (section === "appoint-leader") return people("appoint-leader");
  if (section === "events") return { ...base, workSection: "events" };
  if (section === "create-event") return { ...base, workSection: "events", eventsLaunch: { section: "create" } };
  if (section === "tasks") return { ...base, workSection: "tasks" };
  if (section === "create-task") return { ...base, workSection: "tasks", tasksLaunch: { section: "create", openCreate: true } };
  if (section === "broadcast") return { ...base, commsSection: "tools", toolsLaunch: { section: "broadcast" } };
  if (section === "decisions") return { ...base, overviewView: "decisions" };
  return base;
}

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
  const [launchRoute] = useState<InitialAdminRoute>(() => initialAdminRoute());
  const [group, setGroup] = useState<AdminGroup>(
    launchRoute.peopleSection
      ? "people"
      : launchRoute.workSection
        ? "work"
        : launchRoute.commsSection
          ? "comms"
          : "overview",
  );
  const [peopleSection, setPeopleSection] = useState<PeopleSection | null>(launchRoute.peopleSection);
  const [workSection, setWorkSection] = useState<WorkSection | null>(launchRoute.workSection);
  const [offersInitialSection, setOffersInitialSection] = useState<OffersSection>("applications");
  const [eventsLaunch, setEventsLaunch] = useState<EventsLaunch | null>(launchRoute.eventsLaunch);
  const [projectsLaunch, setProjectsLaunch] = useState<ProjectsLaunch | null>(null);
  const [tasksLaunch, setTasksLaunch] = useState<TasksLaunch | null>(launchRoute.tasksLaunch);
  const [commsSection, setCommsSection] = useState<CommsSection | null>(launchRoute.commsSection);
  const [toolsLaunch, setToolsLaunch] = useState<ToolsLaunch | null>(launchRoute.toolsLaunch);
  const [metricDetail, setMetricDetail] = useState<MetricDetail | null>(null);
  const [showAttendanceProofs, setShowAttendanceProofs] = useState(false);

  const clearSections = () => {
    setPeopleSection(null);
    setWorkSection(null);
    setCommsSection(null);
    setMetricDetail(null);
    setShowAttendanceProofs(false);
    setEventsLaunch(null);
    setProjectsLaunch(null);
    setTasksLaunch(null);
    setToolsLaunch(null);
  };

  const changeGroup = (next: AdminGroup) => {
    setGroup(next);
    clearSections();
  };

  const openPeople = (section: PeopleSection) => {
    setGroup("people");
    clearSections();
    setPeopleSection(section);
  };
  const openWork = (
    section: WorkSection,
    offersSection: OffersSection = "applications",
    launch?: { events?: EventsLaunch | null; projects?: ProjectsLaunch | null; tasks?: TasksLaunch | null },
  ) => {
    setGroup("work");
    clearSections();
    setWorkSection(section);
    if (section === "offers") setOffersInitialSection(offersSection);
    if (section === "events") setEventsLaunch(launch?.events ?? null);
    if (section === "projects") setProjectsLaunch(launch?.projects ?? null);
    if (section === "tasks") setTasksLaunch(launch?.tasks ?? null);
  };
  const openCommsSection = (section: CommsSection, launch?: { tools?: ToolsLaunch | null }) => {
    setGroup("comms");
    clearSections();
    setCommsSection(section);
    if (section === "tools") setToolsLaunch(launch?.tools ?? null);
  };
  const openMetric = (metric: AdminMetricKey, total: number) => {
    setGroup("overview");
    clearSections();
    setMetricDetail({ metric, total });
  };
  const openComms = () => openCommsSection("tools");
  const openBroadcast = () => openCommsSection("tools", { tools: { section: "broadcast" } });
  const openMetricEntity = (entityType: string) => {
    if (entityType === "user") openPeople("participants");
    else if (entityType === "project") openWork("projects");
    else if (entityType === "event" || entityType === "event_registration") openWork("events");
    else if (entityType === "task_submission") openWork("tasks");
  };

  return (
    <div className="era-page" style={{ minHeight: "100vh", display: "flex", flexDirection: "column", minWidth: 0 }}>
      <div style={{ flex: "1 1 auto", minWidth: 0, padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        {group === "overview" && metricDetail && <AdminMetricDetailScreen metric={metricDetail.metric} expectedTotal={metricDetail.total} onBack={() => setMetricDetail(null)} onOpenEntity={(entityType) => openMetricEntity(entityType)} />}
        {group === "overview" && !metricDetail && showAttendanceProofs && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <button type="button" onClick={() => setShowAttendanceProofs(false)} style={{ alignSelf: "flex-start" }}>← Пульт</button>
            <h1 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>Фото-подтверждения</h1>
            <AdminAttendanceProofsScreen />
          </div>
        )}
        {group === "overview" && !metricDetail && !showAttendanceProofs && (
          <AdminOverviewScreen
            onOpenPeople={() => openPeople("participants")}
            onOpenApplications={() => openPeople("applications")}
            onOpenVerification={() => openPeople("verification")}
            onOpenCareer={() => openPeople("career")}
            onOpenProjects={() => openWork("projects")}
            onOpenProjectReview={() => openWork("projects", "applications", { projects: { section: "moderation" } })}
            onOpenEvents={() => openWork("events")}
            onOpenEventCreate={() => openWork("events", "applications", { events: { section: "create" } })}
            onOpenEventModeration={() => openWork("events", "applications", { events: { section: "moderation" } })}
            onOpenEventWaitlist={() => openWork("events", "applications", { events: { section: "operations" } })}
            onOpenActivityResults={() => openWork("events", "applications", { events: { section: "activities", activitiesMode: "review" } })}
            onOpenAttendanceProofs={() => { clearSections(); setGroup("overview"); setShowAttendanceProofs(true); }}
            onOpenTasks={() => openWork("tasks")}
            onOpenTaskCreate={() => openWork("tasks", "applications", { tasks: { section: "create", openCreate: true } })}
            onOpenTaskReview={() => openWork("tasks", "applications", { tasks: { section: "review" } })}
            onOpenOffers={() => openWork("offers", "rewards")}
            onOpenBroadcast={openBroadcast}
            onOpenComms={openComms}
            onOpenMetric={openMetric}
            initialView={launchRoute.overviewView}
          />
        )}

        {group === "people" && !peopleSection && <SectionMenu title="Люди" description="Участники, проверка состава, развитие, портфолио, регистрации, чат лидеров, роли и права на данные." options={PEOPLE_SECTIONS} onOpen={setPeopleSection} />}
        {group === "people" && peopleSection && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <SectionHeader title={PEOPLE_SECTIONS.find((item) => item.value === peopleSection)?.label ?? "Люди"} onBack={() => setPeopleSection(null)} />
            {peopleSection === "participants" && <AdminUsersScreen />}
            {peopleSection === "verification" && <AdminVerificationScreen />}
            {peopleSection === "development" && <AdminDevelopmentScreen />}
            {peopleSection === "career" && <AdminCareerScreen />}
            {peopleSection === "applications" && <AdminApplicationsScreen initialApplicationId={launchRoute.applicationId} />}
            {peopleSection === "leaders-chat" && <AdminWorkcenterScreen />}
            {peopleSection === "appoint-leader" && <AdminAppointLeaderScreen />}
            {peopleSection === "offices" && <AdminOfficesScreen />}
            {peopleSection === "data-rights" && <AdminDataRightsScreen />}
          </div>
        )}

        {group === "work" && !workSection && <SectionMenu title="Работа" description="Создание и управление проектами, мероприятиями, заданиями и возможностями." options={WORK_SECTIONS} onOpen={setWorkSection} />}
        {group === "work" && workSection && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <SectionHeader title={WORK_SECTIONS.find((item) => item.value === workSection)?.label ?? "Работа"} onBack={() => setWorkSection(null)} />
            {workSection === "pulse" && <AdminWorkcenterScreen />}
            {workSection === "projects" && (
              <AdminProjectsScreen key={projectsLaunch?.section ?? "menu"} initialSection={projectsLaunch?.section ?? null} />
            )}
            {workSection === "events" && (
              <AdminEventsScreen
                key={`${eventsLaunch?.section ?? "menu"}:${eventsLaunch?.activitiesMode ?? ""}`}
                initialSection={eventsLaunch?.section ?? null}
                initialActivitiesMode={eventsLaunch?.activitiesMode ?? null}
              />
            )}
            {workSection === "tasks" && (
              <AdminTasksScreen
                key={`${tasksLaunch?.section ?? "menu"}:${tasksLaunch?.openCreate ? "open" : "closed"}`}
                initialSection={tasksLaunch?.section ?? null}
                initialOpenCreate={Boolean(tasksLaunch?.openCreate)}
              />
            )}
            {workSection === "offers" && <AdminOffersScreen key={offersInitialSection} initialSection={offersInitialSection} />}
          </div>
        )}

        {group === "comms" && !commsSection && <SectionMenu title="Связь" description="Чаты, рассылки и обратная связь без системных функций." options={COMMS_SECTIONS} onOpen={setCommsSection} />}
        {group === "comms" && commsSection && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <SectionHeader title={COMMS_SECTIONS.find((item) => item.value === commsSection)?.label ?? "Связь"} onBack={() => setCommsSection(null)} />
            {commsSection === "surveys" && <AdminSurveysScreen />}
            {commsSection === "tools" && (
              <AdminToolsScreen
                key={toolsLaunch?.section ?? "menu"}
                initialSection={toolsLaunch?.section ?? null}
              />
            )}
          </div>
        )}
      </div>
      <AdminBottomNav active={group} onChange={changeGroup} />
    </div>
  );
}
