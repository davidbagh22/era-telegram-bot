import { useCallback, useState } from "react";
import { downloadAnalyticsExcel, fetchAdminAnalyticsSummary, fetchAdminDashboard } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { useToast } from "../../components/Toast";
import { useAsync } from "../../hooks/useAsync";
import type { AnalyticsExcelSection } from "../../types/admin";

const EXCEL_SECTIONS: { value: AnalyticsExcelSection; label: string }[] = [
  { value: "all", label: "📘 Всё" },
  { value: "users", label: "👥 Участники" },
  { value: "departments", label: "🏛 Департаменты" },
  { value: "events", label: "📅 Мероприятия" },
  { value: "projects", label: "💡 Проекты" },
];

const METRIC_LABELS: Record<string, string> = {
  users_total: "Участников всего",
  users_approved: "Одобрено",
  users_pending: "Новые заявки",
  activists: "Активисты",
  leaders: "Лидеры/совет/админы",
  projects_review: "Проекты на проверке",
  projects_active: "Активные проекты",
  events_pending: "События на согласовании",
  events_live: "События в работе",
  tasks_open: "Открытые задачи",
  task_results: "Итоги заданий",
  activity_results: "Активности после мероприятий",
  rewards: "Заявки на возможности",
  portfolio: "Портфолио на проверке",
  reports: "Отчёты",
  questions: "Вопросы",
  departments: "Заявки по направлениям",
};

// Every metric the backend computes, not just the curated subset
// AdminOverviewScreen's Action Center and KPI row show — this is the
// "full breakdown" analytics view, so it's meant to be more exhaustive
// than Обзор, not a repeat of it. See AdminOverviewScreen.tsx for why the
// old attention hero + decision list that used to live here moved there
// instead (this screen is reached from the Аналитика group now, not as
// the Admin Mode landing screen).
const ALL_METRIC_ORDER = [
  "users_total",
  "users_approved",
  "users_pending",
  "activists",
  "leaders",
  "projects_review",
  "projects_active",
  "events_pending",
  "events_live",
  "tasks_open",
  "task_results",
  "activity_results",
  "rewards",
  "portfolio",
  "reports",
  "questions",
  "departments",
];

export function AdminDashboardScreen() {
  const state = useAsync(() => fetchAdminDashboard(), []);
  const analytics = useAsync(() => fetchAdminAnalyticsSummary(), []);
  const [downloadingSection, setDownloadingSection] = useState<AnalyticsExcelSection | null>(null);
  const toast = useToast();

  const handleDownload = useCallback(
    async (section: AnalyticsExcelSection) => {
      setDownloadingSection(section);
      try {
        const blob = await downloadAnalyticsExcel(section);
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `ERA_analytics_${section}.xlsx`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
      } catch {
        toast.show("Не удалось собрать таблицу. Попробуйте ещё раз.", "error");
      } finally {
        setDownloadingSection(null);
      }
    },
    [toast],
  );

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }
  if (state.status === "error") {
    return <EmptyState text="Не удалось загрузить дашборд." />;
  }

  const { metrics } = state.data;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <section>
        <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: "0 0 0.5rem" }}>
          Показатели
        </h2>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {ALL_METRIC_ORDER.map((key) => (
            <Card key={key}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>{METRIC_LABELS[key] ?? key}</span>
                <strong>{metrics[key] ?? 0}</strong>
              </div>
            </Card>
          ))}
        </div>
      </section>

      <section>
        <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: "0 0 0.5rem" }}>
          Аналитика и Excel
        </h2>
        <Card>
          {analytics.status === "ready" && (
            <p style={{ margin: "0 0 0.75rem", color: "var(--era-text-muted)" }}>
              Участников: {analytics.data.total_users} · Мероприятий: {analytics.data.events} · Проектов:{" "}
              {analytics.data.projects} · Организаций: {analytics.data.contacts} · Целей месяца:{" "}
              {analytics.data.goals}
            </p>
          )}
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            {EXCEL_SECTIONS.map((section) => (
              <button
                key={section.value}
                type="button"
                disabled={downloadingSection !== null}
                onClick={() => handleDownload(section.value)}
              >
                {downloadingSection === section.value ? "Готовим…" : section.label}
              </button>
            ))}
          </div>
        </Card>
      </section>
    </div>
  );
}
