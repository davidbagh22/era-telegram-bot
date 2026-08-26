import { useState } from "react";
import type { AdminMetricKey } from "../types/adminMetrics";
import { AdminApplicationsScreen } from "./admin/AdminApplicationsScreen";
import { AdminCareerScreen } from "./admin/AdminCareerScreen";
import { AdminDataRightsScreen } from "./admin/AdminDataRightsScreen";
import { AdminDevelopmentScreen } from "./admin/AdminDevelopmentScreen";
import { AdminEventsScreen } from "./admin/AdminEventsScreen";
import { AdminMetricDetailScreen } from "./admin/AdminMetricDetailScreen";
import { AdminOfficesScreen } from "./admin/AdminOfficesScreen";
import { AdminOffersScreen, type OffersSection } from "./admin/AdminOffersScreen";
import { AdminOverviewScreen } from "./admin/AdminOverviewScreen";
import { AdminProjectsScreen } from "./admin/AdminProjectsScreen";
import { AdminSurveysScreen } from "./admin/AdminSurveysScreen";
import { AdminTasksScreen } from "./admin/AdminTasksScreen";
import { AdminToolsScreen } from "./admin/AdminToolsScreen";
import { AdminUsersScreen } from "./admin/AdminUsersScreen";
import { AdminVerificationScreen } from "./admin/AdminVerificationScreen";

type AdminView =
  | "overview"
  | "participants"
  | "applications"
  | "verification"
  | "development"
  | "career"
  | "offices"
  | "data-rights"
  | "projects"
  | "events"
  | "tasks"
  | "offers"
  | "surveys"
  | "comms";

type MetricDetail = { metric: AdminMetricKey; total: number };

type InitialAdminRoute = {
  view: AdminView;
  applicationId: number | null;
};

const VIEW_TITLES: Record<Exclude<AdminView, "overview">, string> = {
  participants: "Участники",
  applications: "Новые заявки",
  verification: "Проверка состава",
  development: "Состояние и развитие",
  career: "Портфолио и рекомендации",
  offices: "Должности и роли",
  "data-rights": "Данные и права",
  projects: "Проекты",
  events: "Мероприятия",
  tasks: "Задания",
  offers: "Возможности",
  surveys: "Опросы",
  comms: "Центр связи",
};

function initialAdminRoute(): InitialAdminRoute {
  const query = new URLSearchParams(window.location.search);
  const rawSection = query.get("adminSection");
  const known: AdminView[] = [
    "participants",
    "applications",
    "verification",
    "development",
    "career",
    "offices",
    "data-rights",
    "projects",
    "events",
    "tasks",
    "offers",
    "surveys",
    "comms",
  ];
  const view = known.includes(rawSection as AdminView) ? (rawSection as AdminView) : "overview";
  const rawId = query.get("applicationId");
  const parsedId = rawId ? Number(rawId) : NaN;
  return {
    view,
    applicationId: Number.isInteger(parsedId) && parsedId > 0 ? parsedId : null,
  };
}

function WorkspaceHeader({ title, onBack }: { title: string; onBack: () => void }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
      <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← Пульт ЭРА</button>
      <div>
        <p style={{ margin: "0 0 .2rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
          Admin Command Center
        </p>
        <h1 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>{title}</h1>
      </div>
    </div>
  );
}

export function AdminScreen() {
  const [launchRoute] = useState<InitialAdminRoute>(() => initialAdminRoute());
  const [view, setView] = useState<AdminView>(launchRoute.view);
  const [metricDetail, setMetricDetail] = useState<MetricDetail | null>(null);
  const [offersInitialSection, setOffersInitialSection] = useState<OffersSection>("applications");

  const goHome = () => {
    setMetricDetail(null);
    setView("overview");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const open = (next: AdminView) => {
    setMetricDetail(null);
    setView(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const openOffers = (section: OffersSection = "applications") => {
    setOffersInitialSection(section);
    open("offers");
  };

  const openMetric = (metric: AdminMetricKey, total: number) => {
    setMetricDetail({ metric, total });
    setView("overview");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const openMetricEntity = (entityType: string) => {
    if (entityType === "user") open("participants");
    else if (entityType === "project") open("projects");
    else if (entityType === "event" || entityType === "event_registration") open("events");
    else if (entityType === "task_submission") open("tasks");
  };

  const detail = (content: React.ReactNode) => (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <WorkspaceHeader title={VIEW_TITLES[view as Exclude<AdminView, "overview">]} onBack={goHome} />
      {content}
    </div>
  );

  return (
    <div className="era-page" style={{ minHeight: "100vh", minWidth: 0 }}>
      <main style={{ minWidth: 0, padding: "1.25rem 1.25rem var(--era-page-bottom-safe)", display: "flex", flexDirection: "column", gap: "1rem" }}>
        {view === "overview" && metricDetail && (
          <AdminMetricDetailScreen
            metric={metricDetail.metric}
            expectedTotal={metricDetail.total}
            onBack={() => setMetricDetail(null)}
            onOpenEntity={(entityType) => openMetricEntity(entityType)}
          />
        )}

        {view === "overview" && !metricDetail && (
          <AdminOverviewScreen
            onOpenPeople={() => open("participants")}
            onOpenApplications={() => open("applications")}
            onOpenVerification={() => open("verification")}
            onOpenDevelopment={() => open("development")}
            onOpenCareer={() => open("career")}
            onOpenOffices={() => open("offices")}
            onOpenDataRights={() => open("data-rights")}
            onOpenProjects={() => open("projects")}
            onOpenEvents={() => open("events")}
            onOpenTasks={() => open("tasks")}
            onOpenOffers={() => openOffers("rewards")}
            onOpenSurveys={() => open("surveys")}
            onOpenComms={() => open("comms")}
            onOpenMetric={openMetric}
          />
        )}

        {view === "participants" && detail(<AdminUsersScreen />)}
        {view === "applications" && detail(<AdminApplicationsScreen initialApplicationId={launchRoute.applicationId} />)}
        {view === "verification" && detail(<AdminVerificationScreen />)}
        {view === "development" && detail(<AdminDevelopmentScreen />)}
        {view === "career" && detail(<AdminCareerScreen />)}
        {view === "offices" && detail(<AdminOfficesScreen />)}
        {view === "data-rights" && detail(<AdminDataRightsScreen />)}
        {view === "projects" && detail(<AdminProjectsScreen />)}
        {view === "events" && detail(<AdminEventsScreen />)}
        {view === "tasks" && detail(<AdminTasksScreen />)}
        {view === "offers" && detail(<AdminOffersScreen key={offersInitialSection} initialSection={offersInitialSection} />)}
        {view === "surveys" && detail(<AdminSurveysScreen />)}
        {view === "comms" && detail(<AdminToolsScreen />)}
      </main>
    </div>
  );
}
