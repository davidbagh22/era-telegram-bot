import { useCallback, useState } from "react";
import { downloadAnalyticsExcel, fetchAdminAnalyticsSummary, fetchAdminDashboard } from "../../api/client";
import { ActionCell } from "../../components/ActionCell";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { useToast } from "../../components/Toast";
import { useAsync } from "../../hooks/useAsync";
import type { AnalyticsExcelSection } from "../../types/admin";

const EXCEL_SECTIONS: { value: AnalyticsExcelSection; label: string }[] = [
  { value: "all", label: "Всё" },
  { value: "users", label: "Участники" },
  { value: "departments", label: "Департаменты" },
  { value: "events", label: "Мероприятия" },
  { value: "projects", label: "Проекты" },
];

interface AdminDashboardScreenProps {
  onOpenParticipants: () => void;
  onOpenProjects: () => void;
  onOpenEvents: () => void;
  onOpenOrganizations: () => void;
  onOpenGoals: () => void;
  onOpenApplications: () => void;
  onOpenTasks: () => void;
  onOpenOffers: () => void;
}

export function AdminDashboardScreen({
  onOpenParticipants,
  onOpenProjects,
  onOpenEvents,
  onOpenOrganizations,
  onOpenGoals,
  onOpenApplications,
  onOpenTasks,
  onOpenOffers,
}: AdminDashboardScreenProps) {
  const state = useAsync(() => fetchAdminDashboard(), []);
  const analytics = useAsync(() => fetchAdminAnalyticsSummary(), []);
  const [downloadingSection, setDownloadingSection] = useState<AnalyticsExcelSection | null>(null);
  const toast = useToast();

  const handleDownload = useCallback(async (section: AnalyticsExcelSection) => {
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
  }, [toast]);

  if (state.status === "loading" || analytics.status === "loading") return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  if (state.status === "error" || analytics.status === "error") return <EmptyState text="Не удалось загрузить контроль ЭРА." />;

  const { metrics } = state.data;
  const summary = analytics.data;
  const live = [
    { label: "Участники", value: summary.total_users, hint: "Открыть всех участников", icon: "👥", onClick: onOpenParticipants },
    { label: "Проекты", value: summary.projects, hint: "Открыть существующие проекты", icon: "💡", onClick: onOpenProjects },
    { label: "Мероприятия", value: summary.events, hint: "Открыть мероприятия и участников", icon: "📅", onClick: onOpenEvents },
    { label: "Организации", value: summary.contacts, hint: "Открыть партнёров и контакты", icon: "◇", onClick: onOpenOrganizations },
    { label: "Цели месяца", value: summary.goals, hint: "Открыть текущие цели", icon: "◎", onClick: onOpenGoals },
  ];

  const attention = [
    { label: "Новые заявки", value: metrics.users_pending ?? 0, icon: "👤", onClick: onOpenApplications },
    { label: "Проекты на проверке", value: metrics.projects_review ?? 0, icon: "💡", onClick: onOpenProjects },
    { label: "События на согласовании", value: metrics.events_pending ?? 0, icon: "📅", onClick: onOpenEvents },
    { label: "Итоги заданий", value: metrics.task_results ?? 0, icon: "✅", onClick: onOpenTasks },
    { label: "Заявки на возможности", value: metrics.rewards ?? 0, icon: "⭐", onClick: onOpenOffers },
  ].filter((item) => item.value > 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <Card gradient style={{ position: "relative", overflow: "hidden", padding: "1.2rem" }}>
        <div aria-hidden="true" style={{ position: "absolute", inset: 0, background: "radial-gradient(65% 80% at 92% 4%, rgba(255,255,255,0.26), transparent 65%)" }} />
        <div style={{ position: "relative" }}>
          <p style={{ margin: 0, fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase", color: "rgba(255,255,255,.72)" }}>Контроль</p>
          <h2 style={{ margin: "0.2rem 0 0", fontSize: "var(--era-text-3xl)" }}>ЭРА сейчас</h2>
          <p style={{ margin: "0.55rem 0 0", color: "rgba(255,255,255,.82)", lineHeight: 1.45 }}>Не просто цифры. Нажмите на показатель — откроются люди, проекты, события или записи, из которых он сложился.</p>
        </div>
      </Card>

      <section>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.65rem" }}>
          {live.map((item, index) => (
            <button key={item.label} type="button" onClick={item.onClick} style={{ gridColumn: index === live.length - 1 ? "1 / -1" : undefined, textAlign: "left", minHeight: 118, padding: "0.95rem", borderRadius: "1.35rem", border: "1px solid var(--era-border)", background: "linear-gradient(145deg, rgba(255,255,255,.075), rgba(255,255,255,.025))", color: "var(--era-text)", boxShadow: "inset 0 1px rgba(255,255,255,.05)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                <span style={{ fontSize: "1.25rem" }}>{item.icon}</span>
                <strong style={{ fontSize: "1.8rem", lineHeight: 1, fontFamily: "var(--era-font-display)" }}>{item.value}</strong>
              </div>
              <strong style={{ display: "block", marginTop: "0.65rem" }}>{item.label}</strong>
              <span style={{ display: "block", marginTop: "0.2rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>{item.hint} →</span>
            </button>
          ))}
        </div>
      </section>

      <section>
        <h3 style={{ margin: "0 0 0.55rem", fontSize: "var(--era-text-xl)" }}>Требует решения</h3>
        {attention.length === 0 ? (
          <Card style={{ textAlign: "center" }}><strong>Сейчас очереди пусты</strong><p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)" }}>Ничего не ждёт решения администратора.</p></Card>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
            {attention.map((item) => <ActionCell key={item.label} leading={item.icon} title={item.label} meta={String(item.value)} description="Открыть реальные записи" onClick={item.onClick} />)}
          </div>
        )}
      </section>

      <section>
        <h3 style={{ margin: "0 0 0.4rem", fontSize: "var(--era-text-lg)" }}>Выгрузка</h3>
        <p style={{ margin: "0 0 0.6rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>Excel — вторичный инструмент. Для работы с данными используйте показатели выше.</p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
          {EXCEL_SECTIONS.map((section) => (
            <button key={section.value} type="button" disabled={downloadingSection !== null} onClick={() => handleDownload(section.value)}>
              {downloadingSection === section.value ? "Готовим…" : section.label}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
