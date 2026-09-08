import { useCallback, useMemo, useState } from "react";
import {
  downloadAnalyticsSectionTable,
  downloadFullAnalyticsReport,
  downloadOrganizationHealthReport,
  fetchAdminAnalyticsDetails,
  fetchEraEfficiency,
  fetchOrganizationHealth,
  type AnalyticsDetailSection,
  type HealthMetric,
} from "../../api/adminAnalytics";
import { fetchAdminAnalyticsSummary, fetchAdminDashboard } from "../../api/client";
import { fetchMediaAnalytics } from "../../api/media";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { useToast } from "../../components/Toast";
import { useAsync } from "../../hooks/useAsync";
import type { AnalyticsSummary } from "../../types/admin";

const SECTION_META: Record<
  AnalyticsDetailSection,
  { label: string; description: string; value: keyof AnalyticsSummary; accent: string }
> = {
  users: { label: "Участники", description: "Люди, статусы и динамика базы", value: "total_users", accent: "var(--era-red)" },
  events: { label: "Мероприятия", description: "Все события ЭРА", value: "events", accent: "var(--era-gold-ink)" },
  projects: { label: "Проекты", description: "Инициативы и проектная воронка", value: "projects", accent: "var(--era-red-bright)" },
  contacts: { label: "Организации", description: "Партнёрская база", value: "contacts", accent: "var(--era-blue)" },
  goals: { label: "Цели", description: "Цели организации и направлений", value: "goals", accent: "var(--era-gold)" },
};

const STATUS_LABELS: Record<string, string> = {
  approved: "Одобрено",
  pending: "Ожидает",
  needs_info: "Нужны данные",
  rejected: "Отклонено",
  draft: "Черновик",
  published: "Опубликовано",
  registration_open: "Регистрация открыта",
  registration_closed: "Регистрация закрыта",
  active: "Активно",
  initial_review: "Первичная проверка",
  venue_review: "Согласование площадки",
  needs_revision: "Нужна доработка",
  in_progress: "В работе",
  completed: "Завершено",
  done: "Готово",
};

const SIGNAL_GROUPS = [
  { key: "people", label: "Состав", keys: ["approved", "new_30d"] },
  { key: "activity", label: "Активность", keys: ["active_30d", "retention_30d"] },
  { key: "participation", label: "Участие", keys: ["attendance_rate", "feedback"] },
  { key: "projects", label: "Проекты", keys: ["active_projects"] },
  { key: "tasks", label: "Задачи", keys: ["task_delivery", "completed_tasks_30d", "overdue_tasks"] },
  { key: "flow", label: "Рост и очередь", keys: ["growth_conversion", "queue"] },
] as const;

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

function priorityLabel(priority: string): string {
  if (priority === "high") return "Сделать сейчас";
  if (priority === "medium") return "Усилить";
  return "Возможность";
}

function priorityTone(priority: string): "red" | "violet" | "gold" {
  if (priority === "high") return "red";
  if (priority === "medium") return "violet";
  return "gold";
}

function scoreTone(score: number): string {
  if (score >= 70) return "var(--era-gold-ink)";
  if (score >= 40) return "var(--era-gold)";
  return "var(--era-red-bright)";
}

function MiniRing({ score, size = 44 }: { score: number | null; size?: number }) {
  const safeScore = Math.max(0, Math.min(100, score ?? 0));
  const accent = score === null ? "var(--era-ring-track)" : scoreTone(safeScore);
  return (
    <div style={{ width: size, height: size, flexShrink: 0, borderRadius: "50%", padding: 3, background: score === null ? "var(--era-ring-track)" : `conic-gradient(${accent} 0 ${safeScore}%, var(--era-ring-track) ${safeScore}% 100%)` }}>
      <div style={{ width: "100%", height: "100%", borderRadius: "50%", background: "var(--era-surface)", display: "grid", placeItems: "center" }}>
        <strong style={{ fontSize: size * 0.27, lineHeight: 1 }}>{score ?? "—"}</strong>
      </div>
    </div>
  );
}

function SignalCard({ label, metrics }: { label: string; metrics: HealthMetric[] }) {
  const scored = metrics.map((metric) => metric.score).filter((score): score is number => score !== null);
  const score = scored.length ? Math.round(scored.reduce((sum, value) => sum + value, 0) / scored.length) : null;
  const primary = metrics[0];
  const secondary = metrics.slice(1, 3);

  return (
    <Card style={{ padding: "0.8rem", minWidth: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.55rem" }}>
        <MiniRing score={score} />
        <div style={{ minWidth: 0 }}>
          <strong style={{ display: "block", fontSize: "0.86rem" }}>{label}</strong>
          <span style={{ display: "block", marginTop: 2, fontFamily: "var(--era-font-display)", fontWeight: 900, fontSize: "1.15rem", lineHeight: 1.05 }}>{primary?.display ?? "—"}</span>
        </div>
      </div>
      <span style={{ display: "block", marginTop: "0.45rem", color: "var(--era-text-muted)", fontSize: "0.68rem", lineHeight: 1.35 }}>
        {primary?.label ?? "Нет данных"}
        {secondary.map((metric) => ` · ${metric.label}: ${metric.display}`).join("")}
      </span>
    </Card>
  );
}

function RawMetricCard({ metric }: { metric: HealthMetric }) {
  return (
    <Card style={{ padding: "0.7rem 0.8rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "0.6rem", alignItems: "baseline" }}>
        <strong style={{ fontSize: "0.78rem" }}>{metric.label}</strong>
        <strong style={{ whiteSpace: "nowrap" }}>{metric.display}</strong>
      </div>
      <span style={{ display: "block", marginTop: 3, color: "var(--era-text-muted)", fontSize: "0.66rem", lineHeight: 1.3 }}>{metric.note}</span>
    </Card>
  );
}

function DetailView({ section, onBack }: { section: AnalyticsDetailSection; onBack: () => void }) {
  const state = useAsync(() => fetchAdminAnalyticsDetails(section), [section]);
  const meta = SECTION_META[section];
  const toast = useToast();
  const [downloading, setDownloading] = useState(false);

  const downloadTable = async () => {
    setDownloading(true);
    try { saveBlob(await downloadAnalyticsSectionTable(section), `ERA_${section}.xlsx`); }
    catch { toast.show("Не удалось собрать Excel-таблицу.", "error"); }
    finally { setDownloading(false); }
  };

  const downloadFull = async () => {
    setDownloading(true);
    try { saveBlob(await downloadFullAnalyticsReport(), "ERA_full_report.xlsx"); }
    catch { toast.show("Не удалось собрать полный отчёт.", "error"); }
    finally { setDownloading(false); }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
      <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← Аналитика</button>
      <Card gradient>
        <p style={{ margin: 0, opacity: 0.72, fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Раздел аналитики</p>
        <h2 style={{ margin: "0.2rem 0 0", fontSize: "var(--era-text-2xl)" }}>{meta.label}</h2>
        <p style={{ margin: "0.35rem 0 0", opacity: 0.84 }}>{meta.description}</p>
      </Card>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: "0.5rem" }}>
        <button type="button" disabled={downloading} onClick={() => void downloadTable()}>↓ XLSX</button>
        <button type="button" className="era-btn-primary" disabled={downloading} onClick={() => void downloadFull()}>↓ Полный XLSX</button>
      </div>
      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить записи." />}
      {state.status === "ready" && (
        <>
          <Card style={{ padding: "0.75rem 0.9rem", background: "var(--era-surface-2)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.75rem" }}><strong>Записей в системе</strong><strong style={{ fontSize: "1.6rem" }}>{state.data.total}</strong></div>
          </Card>
          {state.data.items.length === 0 ? <EmptyState text="Записей пока нет." /> : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {state.data.items.map((item) => (
                <Card key={`${section}-${item.id}`} style={{ padding: "0.8rem 0.9rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "flex-start" }}>
                    <div style={{ minWidth: 0 }}><strong style={{ display: "block", overflowWrap: "break-word" }}>{item.title}</strong>{item.subtitle && <span style={{ display: "block", marginTop: "0.25rem", color: "var(--era-text-muted)", fontSize: "0.78rem", overflowWrap: "break-word" }}>{item.subtitle}</span>}</div>
                    {item.status && <StatusBadge label={STATUS_LABELS[item.status] ?? item.status} tone="neutral" />}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function AdminDashboardScreen() {
  const dashboard = useAsync(() => fetchAdminDashboard(), []);
  const analytics = useAsync(() => fetchAdminAnalyticsSummary(), []);
  const efficiency = useAsync(() => fetchEraEfficiency(), []);
  const health = useAsync(() => fetchOrganizationHealth(), []);
  const mediaAnalytics = useAsync(() => fetchMediaAnalytics(), []);
  const [selectedSection, setSelectedSection] = useState<AnalyticsDetailSection | null>(null);
  const [downloadingSection, setDownloadingSection] = useState<AnalyticsDetailSection | "all" | "health" | null>(null);
  const [showRawMetrics, setShowRawMetrics] = useState(false);
  const toast = useToast();

  const handleSectionDownload = useCallback(async (section: AnalyticsDetailSection) => {
    setDownloadingSection(section);
    try { saveBlob(await downloadAnalyticsSectionTable(section), `ERA_${section}.xlsx`); }
    catch { toast.show("Не удалось собрать Excel-таблицу.", "error"); }
    finally { setDownloadingSection(null); }
  }, [toast]);

  const handleHealthReport = useCallback(async () => {
    setDownloadingSection("health");
    try { saveBlob(await downloadOrganizationHealthReport(), "ERA_organization_health.xlsx"); }
    catch { toast.show("Не удалось собрать здоровье организации.", "error"); }
    finally { setDownloadingSection(null); }
  }, [toast]);

  const handleFullReport = useCallback(async () => {
    setDownloadingSection("all");
    try { saveBlob(await downloadFullAnalyticsReport(), "ERA_full_report.xlsx"); }
    catch { toast.show("Не удалось собрать полный отчёт.", "error"); }
    finally { setDownloadingSection(null); }
  }, [toast]);

  const signals = useMemo(() => {
    if (health.status !== "ready") return [];
    const byKey = new Map(health.data.metrics.map((metric) => [metric.key, metric]));
    return SIGNAL_GROUPS.map((group) => ({
      ...group,
      metrics: group.keys.map((key) => byKey.get(key)).filter((metric): metric is HealthMetric => Boolean(metric)),
    }));
  }, [health]);

  const rawGroups = useMemo(() => {
    if (health.status !== "ready") return [] as { category: string; metrics: HealthMetric[] }[];
    const groups = new Map<string, HealthMetric[]>();
    health.data.metrics.forEach((metric) => groups.set(metric.category, [...(groups.get(metric.category) ?? []), metric]));
    return Array.from(groups.entries()).map(([category, metrics]) => ({ category, metrics }));
  }, [health]);

  if (selectedSection) return <DetailView section={selectedSection} onBack={() => setSelectedSection(null)} />;
  if (dashboard.status === "loading" || analytics.status === "loading" || efficiency.status === "loading" || health.status === "loading") return <p style={{ color: "var(--era-text-muted)" }}>Собираем аналитику ЭРА…</p>;
  if (dashboard.status === "error" || analytics.status === "error" || efficiency.status === "error" || health.status === "error") return <EmptyState text="Не удалось загрузить аналитику. Попробуйте ещё раз." />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <Card style={{ padding: "1rem", background: "radial-gradient(circle at 92% 0%, rgba(99,44,255,.16), transparent 42%), var(--era-surface)" }}>
        <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Аналитика ЭРА</p>
        <h2 style={{ margin: "0.2rem 0 0", fontSize: "var(--era-text-2xl)" }}>Главное на одном экране</h2>
        <p style={{ margin: "0.4rem 0 0", color: "var(--era-text-muted)", fontSize: "0.78rem", lineHeight: 1.4 }}>Вместо десятков отдельных метрик — шесть смысловых сигналов. Исходные показатели сохранены ниже в детализации.</p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: "0.6rem", marginTop: "0.85rem" }}>
          <Card style={{ padding: "0.75rem", background: "var(--era-surface-2)" }}><strong style={{ display: "block", fontSize: "1.6rem" }}>{efficiency.data.score}</strong><span style={{ fontSize: "0.76rem" }}>Эффективность</span><span style={{ display: "block", color: "var(--era-text-muted)", fontSize: "0.66rem" }}>{efficiency.data.label}</span></Card>
          <Card style={{ padding: "0.75rem", background: "var(--era-surface-2)" }}><strong style={{ display: "block", fontSize: "1.6rem" }}>{health.data.pulse_suppressed ? "—" : health.data.pulse}</strong><span style={{ fontSize: "0.76rem" }}>Пульс</span><span style={{ display: "block", color: "var(--era-text-muted)", fontSize: "0.66rem" }}>{health.data.pulse_label}</span></Card>
        </div>
      </Card>

      <section>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "end", gap: "0.6rem", marginBottom: "0.55rem" }}><div><p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Ключевые показатели</p><h3 style={{ margin: "0.15rem 0 0" }}>6 сигналов</h3></div><StatusBadge label="6" tone="gold" /></div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: "0.5rem" }}>
          {signals.map((signal) => <SignalCard key={signal.key} label={signal.label} metrics={signal.metrics} />)}
        </div>
      </section>

      {health.data.risks.length > 0 && (
        <section>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "end", marginBottom: "0.55rem" }}><h3 style={{ margin: 0 }}>Сигналы внимания</h3><StatusBadge label={`${health.data.risks.length}`} tone="red" /></div>
          <div style={{ display: "grid", gap: "0.5rem" }}>{health.data.risks.slice(0, 5).map((risk, index) => <Card key={`${risk}-${index}`} style={{ padding: "0.75rem 0.85rem", borderLeft: "3px solid var(--era-red)" }}><span style={{ fontSize: "0.8rem", lineHeight: 1.45 }}>{risk}</span></Card>)}</div>
        </section>
      )}

      <section>
        <button type="button" onClick={() => setShowRawMetrics((value) => !value)} style={{ width: "100%" }}>{showRawMetrics ? "Скрыть исходные показатели" : "Открыть исходные показатели"}</button>
        {showRawMetrics && <div style={{ marginTop: "0.65rem" }}>{rawGroups.map(({ category, metrics }) => <div key={category} style={{ marginBottom: "0.8rem" }}><strong style={{ display: "block", marginBottom: "0.4rem", color: "var(--era-text-muted)", fontSize: "0.7rem", textTransform: "uppercase" }}>{category}</strong><div style={{ display: "grid", gap: "0.4rem" }}>{metrics.map((metric) => <RawMetricCard key={metric.key} metric={metric} />)}</div></div>)}</div>}
      </section>

      {mediaAnalytics.status === "ready" && (
        <section>
          <div style={{ marginBottom: "0.55rem" }}><p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Подразделение</p><h3 style={{ margin: "0.15rem 0 0" }}>Медиа</h3></div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: "0.5rem" }}>
            <Card style={{ padding: "0.75rem" }}><strong style={{ display: "block", fontSize: "1.3rem" }}>{mediaAnalytics.data.published}</strong><span style={{ fontSize: "0.75rem" }}>публикаций</span></Card>
            <Card style={{ padding: "0.75rem" }}><strong style={{ display: "block", fontSize: "1.3rem" }}>{mediaAnalytics.data.chat_messages_period}</strong><span style={{ fontSize: "0.75rem" }}>сообщений в чате</span></Card>
            <Card style={{ padding: "0.75rem" }}><strong style={{ display: "block", fontSize: "1.3rem" }}>{mediaAnalytics.data.tasks_completed}/{mediaAnalytics.data.tasks_created}</strong><span style={{ fontSize: "0.75rem" }}>медиа-задач</span></Card>
            <Card style={{ padding: "0.75rem" }}><strong style={{ display: "block", fontSize: "1.3rem" }}>{mediaAnalytics.data.on_time_rate == null ? "—" : `${mediaAnalytics.data.on_time_rate}%`}</strong><span style={{ fontSize: "0.75rem" }}>вышло вовремя</span></Card>
          </div>
        </section>
      )}

      <section>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.6rem", alignItems: "end", marginBottom: "0.55rem" }}><div><p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Эта неделя</p><h3 style={{ margin: "0.15rem 0 0" }}>Что делать дальше</h3></div><StatusBadge label={`${efficiency.data.recommendations.length}`} tone="violet" /></div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>{efficiency.data.recommendations.slice(0, 5).map((item, index) => <Card key={`${item.title}-${index}`} style={{ padding: "0.8rem" }}><div style={{ display: "flex", justifyContent: "space-between", gap: "0.6rem", alignItems: "flex-start" }}><strong style={{ fontSize: "0.9rem" }}>{item.title}</strong><StatusBadge label={priorityLabel(item.priority)} tone={priorityTone(item.priority)} /></div><p style={{ margin: "0.4rem 0 0", color: "var(--era-text-muted)", fontSize: "0.75rem", lineHeight: 1.4 }}>{item.reason}</p><p style={{ margin: "0.4rem 0 0", fontSize: "0.8rem" }}><strong>→ {item.action}</strong></p></Card>)}</div>
      </section>

      <section>
        <div style={{ marginBottom: "0.55rem" }}><p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Данные по объектам</p><h3 style={{ margin: "0.15rem 0 0" }}>Открыть или выгрузить</h3></div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {(Object.keys(SECTION_META) as AnalyticsDetailSection[]).map((section) => { const meta = SECTION_META[section]; return <Card key={section} style={{ padding: "0.8rem", borderLeft: `3px solid ${meta.accent}` }}><div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: "0.6rem", alignItems: "center" }}><button type="button" onClick={() => setSelectedSection(section)} style={{ border: 0, background: "transparent", padding: 0, textAlign: "left", color: "inherit", minHeight: 0, minWidth: 0 }}><strong style={{ display: "block", fontSize: "1.35rem" }}>{analytics.data[meta.value]}</strong><strong style={{ display: "block" }}>{meta.label}</strong><span style={{ display: "block", color: "var(--era-text-muted)", fontSize: "0.7rem" }}>{meta.description} →</span></button><button type="button" disabled={downloadingSection !== null} onClick={() => void handleSectionDownload(section)} style={{ padding: "0.45rem 0.55rem", minHeight: "2.35rem" }}>{downloadingSection === section ? "…" : "↓ XLSX"}</button></div></Card>; })}
        </div>
      </section>

      <div style={{ display: "grid", gap: "0.5rem" }}>
        <button type="button" className="era-btn-primary" disabled={downloadingSection !== null} onClick={() => void handleHealthReport()} style={{ width: "100%" }}>{downloadingSection === "health" ? "Собираем…" : "↓ Здоровье организации · XLSX"}</button>
        <button type="button" disabled={downloadingSection !== null} onClick={() => void handleFullReport()} style={{ width: "100%" }}>{downloadingSection === "all" ? "Собираем…" : "↓ Полный отчёт ЭРА · XLSX"}</button>
      </div>

      <Card style={{ padding: "0.8rem" }}><div style={{ display: "flex", justifyContent: "space-between", gap: "0.7rem", alignItems: "center" }}><div><strong>{dashboard.data.attention_total > 0 ? "Есть решения на очереди" : "Очередь чистая"}</strong><p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "0.74rem" }}>{dashboard.data.attention_total > 0 ? `${dashboard.data.attention_total} записей требуют решения.` : "Ничего не ждёт проверки или ответа."}</p></div><strong style={{ fontSize: "1.5rem" }}>{dashboard.data.attention_total}</strong></div></Card>
      <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.66rem", lineHeight: 1.4 }}>{health.data.data_note}</p>
    </div>
  );
}
