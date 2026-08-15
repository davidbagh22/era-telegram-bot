import { useCallback, useState } from "react";
import {
  downloadAnalyticsSectionCsv,
  downloadAnalyticsSectionXlsx,
  downloadFullAnalyticsReport,
  fetchAdminAnalyticsDetails,
  fetchEraEfficiency,
  type AnalyticsDetailSection,
  type EfficiencyMetric,
} from "../../api/adminAnalytics";
import { fetchAdminAnalyticsSummary, fetchAdminDashboard } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { PageHeader } from "../../components/PageHeader";
import { PrimaryButton, SecondaryButton } from "../../components/Buttons";
import { SkeletonCard, SkeletonList } from "../../components/Skeleton";
import { StatusBadge } from "../../components/StatusBadge";
import { StatusOrbit } from "../../components/StatusOrbit";
import { ChevronRightIcon } from "../../components/icons";
import { useToast } from "../../components/Toast";
import { useAsync } from "../../hooks/useAsync";
import type { AnalyticsSummary } from "../../types/admin";

const SECTION_META: Record<AnalyticsDetailSection, { label: string; description: string; value: keyof AnalyticsSummary }> = {
  users: { label: "Участники", description: "Люди, статусы и динамика базы", value: "total_users" },
  events: { label: "События", description: "Все мероприятия ЭРА", value: "events" },
  projects: { label: "Проекты", description: "Инициативы и проектная воронка", value: "projects" },
  contacts: { label: "Организации", description: "Партнёрская база", value: "contacts" },
  goals: { label: "Цели", description: "Цели организации и направлений", value: "goals" },
};

const STATUS_LABELS: Record<string, string> = {
  approved: "Одобрено", pending: "Ожидает", needs_info: "Нужны данные", rejected: "Отклонено",
  draft: "Черновик", published: "Опубликовано", registration_open: "Регистрация открыта",
  registration_closed: "Регистрация закрыта", active: "Активно", initial_review: "Первичная проверка",
  venue_review: "Согласование площадки", needs_revision: "Нужна доработка", in_progress: "В работе",
  completed: "Завершено", done: "Готово",
};

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function metricSection(metric: EfficiencyMetric): AnalyticsDetailSection | null {
  if (metric.key === "engagement" || metric.key === "growth") return "users";
  if (metric.key === "events" || metric.key === "registrations" || metric.key === "feedback") return "events";
  if (metric.key === "projects") return "projects";
  return null;
}

function priorityLabel(priority: string): string {
  if (priority === "high") return "Сделать сейчас";
  if (priority === "medium") return "Усилить";
  return "Возможность";
}

function priorityTone(priority: string): "red" | "neutral" | "gold" {
  if (priority === "high") return "red";
  if (priority === "medium") return "neutral";
  return "gold";
}

function DetailView({ section, onBack }: { section: AnalyticsDetailSection; onBack: () => void }) {
  const state = useAsync(() => fetchAdminAnalyticsDetails(section), [section]);
  const meta = SECTION_META[section];
  const toast = useToast();
  const [downloading, setDownloading] = useState<"csv" | "xlsx" | "full" | null>(null);

  const download = async (kind: "csv" | "xlsx" | "full") => {
    if (downloading) return;
    setDownloading(kind);
    try {
      if (kind === "csv") saveBlob(await downloadAnalyticsSectionCsv(section), `ERA_${section}.csv`);
      else if (kind === "xlsx") saveBlob(await downloadAnalyticsSectionXlsx(section), `ERA_${section}.xlsx`);
      else saveBlob(await downloadFullAnalyticsReport(), "ERA_full_report.xlsx");
    } catch { toast.show("Не удалось собрать файл. Попробуйте снова.", "error"); }
    finally { setDownloading(null); }
  };

  return (
    <div className="era-page" style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
      <PageHeader title={meta.label} eyebrow="Аналитика ЭРА" subtitle={meta.description} onBack={onBack} />
      <div className="era-grid-2">
        <SecondaryButton busy={downloading === "csv"} onClick={() => void download("csv")}>↓ CSV</SecondaryButton>
        <SecondaryButton busy={downloading === "xlsx"} onClick={() => void download("xlsx")}>↓ XLSX</SecondaryButton>
      </div>
      <PrimaryButton busy={downloading === "full"} onClick={() => void download("full")}>Полный отчёт XLSX</PrimaryButton>

      {state.status === "loading" && <SkeletonList count={4} />}
      {state.status === "error" && <EmptyState title="Записи не загрузились" description="Цифры не подменяются. Попробуйте открыть раздел ещё раз." />}
      {state.status === "ready" && <>
        <Card style={{ boxShadow: "none" }}><span className="era-kicker">Реальных записей</span><strong style={{ display: "block", marginTop: 5, fontSize: "2rem" }}>{state.data.total}</strong></Card>
        {state.data.items.length === 0 ? <EmptyState title="Записей пока нет" description="Когда данные появятся в системе, они автоматически попадут сюда." /> : <div style={{ display: "grid", gap: "0.6rem" }}>{state.data.items.map((item) => (
          <Card key={`${section}-${item.id}`} style={{ boxShadow: "none" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "flex-start" }}>
              <div style={{ minWidth: 0 }}><strong style={{ display: "block", overflowWrap: "anywhere" }}>{item.title}</strong>{item.subtitle && <span style={{ display: "block", marginTop: 3, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>{item.subtitle}</span>}</div>
              {item.status && <StatusBadge label={STATUS_LABELS[item.status] ?? item.status} tone="neutral" />}
            </div>
          </Card>
        ))}</div>}
      </>}
    </div>
  );
}

interface AdminDashboardScreenProps {
  onCreateActivity?: (topic?: string) => void;
}

export function AdminDashboardScreen({ onCreateActivity }: AdminDashboardScreenProps) {
  const dashboard = useAsync(() => fetchAdminDashboard(), []);
  const analytics = useAsync(() => fetchAdminAnalyticsSummary(), []);
  const efficiency = useAsync(() => fetchEraEfficiency(), []);
  const [selectedSection, setSelectedSection] = useState<AnalyticsDetailSection | null>(null);
  const [downloading, setDownloading] = useState(false);
  const toast = useToast();

  const fullReport = useCallback(async () => {
    if (downloading) return;
    setDownloading(true);
    try { saveBlob(await downloadFullAnalyticsReport(), "ERA_full_report.xlsx"); }
    catch { toast.show("Не удалось собрать полный отчёт.", "error"); }
    finally { setDownloading(false); }
  }, [downloading, toast]);

  if (selectedSection) return <DetailView section={selectedSection} onBack={() => setSelectedSection(null)} />;
  if (dashboard.status === "loading" || analytics.status === "loading" || efficiency.status === "loading") return <div style={{ display: "grid", gap: "0.75rem" }}><SkeletonCard /><SkeletonCard /><SkeletonCard /></div>;
  if (dashboard.status === "error" || analytics.status === "error" || efficiency.status === "error") return <EmptyState title="Аналитика не загрузилась" description="Данные не заменяются примерными цифрами. Попробуйте открыть экран снова." />;

  const score = efficiency.data.score;

  return (
    <div className="era-page" style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <Card style={{ padding: "1.1rem", borderColor: "rgba(227,38,54,.14)", background: "linear-gradient(145deg,rgba(227,38,54,.045),rgba(197,162,100,.045)),#fff" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <StatusOrbit percent={score} size={118} strokeWidth={9} label={`ERA PULSE ${score} из 100`}><div><strong style={{ display: "block", fontSize: "1.6rem", lineHeight: 1 }}>{score}</strong><span style={{ color: "var(--era-text-muted)", fontSize: "0.65rem" }}>/ 100</span></div></StatusOrbit>
          <div style={{ flex: 1, minWidth: 0 }}><p className="era-kicker">ERA PULSE</p><h2 style={{ margin: "0.25rem 0 0", fontSize: "var(--era-text-2xl)" }}>{efficiency.data.label}</h2><p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>{efficiency.data.period_label}</p></div>
        </div>
        <p style={{ margin: "0.8rem 0 0", paddingTop: "0.75rem", borderTop: "1px solid var(--era-border)", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>{efficiency.data.data_note}</p>
      </Card>

      <section className="era-section">
        <div><p className="era-kicker">Из чего считается</p><h2 className="era-section-title" style={{ marginTop: 4 }}>Пульс организации</h2></div>
        <div className="era-grid-2">{efficiency.data.metrics.map((metric) => {
          const section = metricSection(metric);
          return <Card key={metric.key} interactive={Boolean(section)} onClick={section ? () => setSelectedSection(section) : undefined} ariaLabel={section ? `${metric.label}: ${metric.display}. Открыть реальные данные` : undefined} style={{ boxShadow: "none", minHeight: 130 }}><strong style={{ display: "block", fontSize: "1.55rem" }}>{metric.display}</strong><span style={{ display: "block", marginTop: 4, fontWeight: 850, fontSize: "var(--era-text-sm)" }}>{metric.label}</span>{metric.score !== null && <span style={{ display: "block", marginTop: 4, color: "var(--era-red)", fontSize: "var(--era-text-xs)", fontWeight: 800 }}>{metric.score}/100</span>}<span style={{ display: "block", marginTop: 5, color: "var(--era-text-muted)", fontSize: "0.7rem", lineHeight: 1.35 }}>{metric.note}</span>{section && <ChevronRightIcon width={17} height={17} style={{ position: "absolute", opacity: 0 }} />}</Card>;
        })}</div>
      </section>

      <section className="era-section">
        <div><p className="era-kicker">Управленческий вывод</p><h2 className="era-section-title" style={{ marginTop: 4 }}>Что сделать на этой неделе</h2></div>
        {efficiency.data.recommendations.map((item, index) => <Card key={`${item.title}-${index}`} style={{ boxShadow: "none" }}><div style={{ display: "flex", justifyContent: "space-between", gap: "0.6rem", alignItems: "flex-start" }}><strong>{item.title}</strong><StatusBadge label={priorityLabel(item.priority)} tone={priorityTone(item.priority)} /></div><p style={{ margin: "0.45rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>{item.reason}</p><p style={{ margin: "0.5rem 0 0", fontSize: "var(--era-text-sm)" }}><strong>{item.action}</strong></p>{onCreateActivity && item.priority === "opportunity" && efficiency.data.top_interest && item.title.includes(efficiency.data.top_interest) && <PrimaryButton onClick={() => onCreateActivity(efficiency.data.top_interest ?? undefined)} style={{ width: "100%", marginTop: "0.75rem" }}>Создать активность →</PrimaryButton>}</Card>)}
      </section>

      {efficiency.data.top_interest && <Card style={{ borderColor: "rgba(197,162,100,.28)" }}><p className="era-kicker" style={{ color: "var(--era-gold-ink)" }}>Сильный интерес</p><strong style={{ display: "block", marginTop: 4, fontSize: "var(--era-text-xl)" }}>{efficiency.data.top_interest}</strong><p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)" }}>{efficiency.data.top_interest_count} профилей дают этот сигнал. Это не прогноз — это данные анкет.</p>{onCreateActivity && <PrimaryButton onClick={() => onCreateActivity(efficiency.data.top_interest ?? undefined)} style={{ width: "100%", marginTop: "0.75rem" }}>Создать активность →</PrimaryButton>}</Card>}

      <section className="era-section">
        <h2 className="era-section-title">Все данные</h2>
        <div style={{ display: "grid", gap: "0.55rem" }}>{(Object.keys(SECTION_META) as AnalyticsDetailSection[]).map((section) => { const meta = SECTION_META[section]; const value = analytics.data[meta.value]; return <button key={section} type="button" onClick={() => setSelectedSection(section)} style={{ width: "100%", minHeight: 64, padding: "0.75rem 0.85rem", display: "flex", gap: "0.75rem", alignItems: "center", textAlign: "left", background: "#fff" }}><strong style={{ fontSize: "1.45rem", minWidth: 48 }}>{value}</strong><span style={{ flex: 1 }}><strong>{meta.label}</strong><span style={{ display: "block", marginTop: 2, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>{meta.description}</span></span><ChevronRightIcon width={19} height={19} /></button>; })}</div>
      </section>

      <PrimaryButton busy={downloading} busyLabel="Собираем отчёт…" onClick={() => void fullReport()}>↓ Полный отчёт XLSX</PrimaryButton>
      <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", textAlign: "center" }}>Отчёт включает исходные показатели, расчёт ERA PULSE и рекомендации, основанные на тех же реальных данных.</p>
    </div>
  );
}
