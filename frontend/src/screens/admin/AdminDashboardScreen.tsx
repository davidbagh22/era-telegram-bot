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
  users: {
    label: "Участники",
    description: "Люди, статусы и динамика базы",
    value: "total_users",
    accent: "var(--era-red)",
  },
  events: {
    label: "Мероприятия",
    description: "Все события ЭРА",
    value: "events",
    accent: "var(--era-gold-ink)",
  },
  projects: {
    label: "Проекты",
    description: "Инициативы и проектная воронка",
    value: "projects",
    accent: "var(--era-red-bright)",
  },
  contacts: {
    label: "Организации",
    description: "Партнёрская база",
    value: "contacts",
    accent: "var(--era-blue)",
  },
  goals: {
    label: "Цели",
    description: "Цели организации и направлений",
    value: "goals",
    accent: "var(--era-gold)",
  },
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

const EXECUTIVE_KEYS = new Set([
  "approved",
  "new_30d",
  "active_30d",
  "retention_30d",
  "growth_conversion",
  "attendance_rate",
  "feedback",
  "active_projects",
  "completed_tasks_30d",
  "overdue_tasks",
  "queue",
  "task_delivery",
]);

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

function ScoreRing({ score, label, muted = false }: { score: number | null; label: string; muted?: boolean }) {
  const safeScore = Math.max(0, Math.min(100, score ?? 0));
  return (
    <div
      aria-label={`${label}: ${score ?? "нет данных"}${score === null ? "" : " из 100"}`}
      style={{
        width: 104,
        height: 104,
        borderRadius: "50%",
        padding: 7,
        background: score === null
          ? "var(--era-ring-track)"
          : `conic-gradient(${muted ? "var(--era-gold-ink)" : "var(--era-red-bright)"} 0 ${safeScore}%, var(--era-ring-track) ${safeScore}% 100%)`,
        boxShadow: score === null ? "none" : "0 0 28px rgba(99,44,255,0.14)",
      }}
    >
      <div style={{ width: "100%", height: "100%", borderRadius: "50%", background: "var(--era-surface)", display: "grid", placeItems: "center", textAlign: "center" }}>
        <div>
          <strong style={{ display: "block", fontFamily: "var(--era-font-display)", fontSize: "1.75rem", lineHeight: 1 }}>{score ?? "—"}</strong>
          <span style={{ color: "var(--era-text-muted)", fontSize: "0.64rem", fontWeight: 800 }}>{score === null ? "НЕТ ДАННЫХ" : "/ 100"}</span>
        </div>
      </div>
    </div>
  );
}

function MetricCard({ metric }: { metric: HealthMetric }) {
  return (
    <Card style={{ padding: "0.75rem 0.8rem" }}>
      <strong style={{ display: "block", fontFamily: "var(--era-font-display)", fontSize: "1.25rem" }}>{metric.display}</strong>
      <span style={{ display: "block", marginTop: "0.18rem", fontWeight: 800, fontSize: "0.78rem" }}>{metric.label}</span>
      <span style={{ display: "block", marginTop: "0.22rem", color: "var(--era-text-muted)", fontSize: "0.69rem", lineHeight: 1.35 }}>{metric.note}</span>
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
    try {
      saveBlob(await downloadAnalyticsSectionTable(section), `ERA_${section}.xlsx`);
    } catch {
      toast.show("Не удалось собрать Excel-таблицу.", "error");
    } finally {
      setDownloading(false);
    }
  };

  const downloadFull = async () => {
    setDownloading(true);
    try {
      saveBlob(await downloadFullAnalyticsReport(), "ERA_full_report.xlsx");
    } catch {
      toast.show("Не удалось собрать полный отчёт.", "error");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
      <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← Аналитика</button>

      <Card gradient>
        <p style={{ margin: 0, opacity: 0.72, fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Раздел аналитики</p>
        <h2 style={{ margin: "0.2rem 0 0", fontSize: "var(--era-text-2xl)" }}>{meta.label}</h2>
        <p style={{ margin: "0.35rem 0 0", opacity: 0.84 }}>{meta.description}</p>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
        <button type="button" disabled={downloading} onClick={() => void downloadTable()}>↓ XLSX</button>
        <button type="button" className="era-btn-primary" disabled={downloading} onClick={() => void downloadFull()}>↓ Полный XLSX</button>
      </div>

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить записи." />}
      {state.status === "ready" && (
        <>
          <Card style={{ padding: "0.75rem 0.9rem", background: "var(--era-surface-2)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.75rem" }}>
              <strong>Записей в системе</strong>
              <strong style={{ fontFamily: "var(--era-font-display)", fontSize: "1.6rem" }}>{state.data.total}</strong>
            </div>
          </Card>

          {state.data.items.length === 0 ? <EmptyState text="Записей пока нет." /> : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {state.data.items.map((item) => (
                <Card key={`${section}-${item.id}`} style={{ padding: "0.8rem 0.9rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "flex-start" }}>
                    <div style={{ minWidth: 0 }}>
                      <strong style={{ display: "block", overflowWrap: "anywhere" }}>{item.title}</strong>
                      {item.subtitle && <span style={{ display: "block", marginTop: "0.25rem", color: "var(--era-text-muted)", fontSize: "0.78rem", overflowWrap: "anywhere" }}>{item.subtitle}</span>}
                    </div>
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
  const [selectedSection, setSelectedSection] = useState<AnalyticsDetailSection | null>(null);
  const [downloadingSection, setDownloadingSection] = useState<AnalyticsDetailSection | "all" | "health" | null>(null);
  const [showAllMetrics, setShowAllMetrics] = useState(false);
  const toast = useToast();

  const handleSectionDownload = useCallback(async (section: AnalyticsDetailSection) => {
    setDownloadingSection(section);
    try {
      saveBlob(await downloadAnalyticsSectionTable(section), `ERA_${section}.xlsx`);
    } catch {
      toast.show("Не удалось собрать Excel-таблицу.", "error");
    } finally {
      setDownloadingSection(null);
    }
  }, [toast]);

  const handleHealthReport = useCallback(async () => {
    setDownloadingSection("health");
    try {
      saveBlob(await downloadOrganizationHealthReport(), "ERA_organization_health.xlsx");
    } catch {
      toast.show("Не удалось собрать здоровье организации.", "error");
    } finally {
      setDownloadingSection(null);
    }
  }, [toast]);

  const handleFullReport = useCallback(async () => {
    setDownloadingSection("all");
    try {
      saveBlob(await downloadFullAnalyticsReport(), "ERA_full_report.xlsx");
    } catch {
      toast.show("Не удалось собрать полный отчёт.", "error");
    } finally {
      setDownloadingSection(null);
    }
  }, [toast]);

  const groupedMetrics = useMemo(() => {
    if (health.status !== "ready") return [] as [string, HealthMetric[]][];
    const visible = showAllMetrics ? health.data.metrics : health.data.metrics.filter((metric) => EXECUTIVE_KEYS.has(metric.key));
    const groups = new Map<string, HealthMetric[]>();
    visible.forEach((metric) => groups.set(metric.category, [...(groups.get(metric.category) ?? []), metric]));
    return Array.from(groups.entries());
  }, [health, showAllMetrics]);

  if (selectedSection) return <DetailView section={selectedSection} onBack={() => setSelectedSection(null)} />;

  if (dashboard.status === "loading" || analytics.status === "loading" || efficiency.status === "loading" || health.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Собираем аналитику ЭРА…</p>;
  }
  if (dashboard.status === "error" || analytics.status === "error" || efficiency.status === "error" || health.status === "error") {
    return <EmptyState text="Не удалось загрузить аналитику. Данные не подменяются — попробуйте ещё раз." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <Card style={{ padding: "1rem", background: "radial-gradient(circle at 92% 0%, rgba(99,44,255,.16), transparent 42%), var(--era-surface)" }}>
        <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Здоровье ЭРА</p>
        <h2 style={{ margin: "0.2rem 0 0", fontSize: "var(--era-text-2xl)" }}>Два сигнала. Одна картина.</h2>
        <p style={{ margin: "0.45rem 0 0", color: "var(--era-text-muted)", fontSize: "0.78rem", lineHeight: 1.45 }}>
          Эффективность показывает, как работает система. Пульс — как в среднем чувствует себя сообщество по пяти текущим областям «Моего вектора».
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.65rem", marginTop: "0.9rem" }}>
          <div style={{ display: "grid", justifyItems: "center", textAlign: "center", gap: "0.45rem", padding: "0.8rem 0.45rem", border: "1px solid var(--era-border)", borderRadius: "var(--era-radius-card)", background: "var(--era-surface-2)" }}>
            <ScoreRing score={efficiency.data.score} label="Эффективность ЭРА" />
            <div><strong>Эффективность</strong><span style={{ display: "block", color: "var(--era-text-muted)", fontSize: "0.68rem", marginTop: 3 }}>{efficiency.data.label}</span></div>
          </div>
          <div style={{ display: "grid", justifyItems: "center", textAlign: "center", gap: "0.45rem", padding: "0.8rem 0.45rem", border: "1px solid var(--era-border)", borderRadius: "var(--era-radius-card)", background: "var(--era-surface-2)" }}>
            <ScoreRing score={health.data.pulse_suppressed ? null : health.data.pulse} label="Пульс организации" muted />
            <div><strong>Пульс</strong><span style={{ display: "block", color: "var(--era-text-muted)", fontSize: "0.68rem", marginTop: 3 }}>{health.data.pulse_label}</span></div>
          </div>
        </div>
        <p style={{ margin: "0.7rem 0 0", color: "var(--era-text-muted)", fontSize: "0.69rem", lineHeight: 1.45 }}>
          Пульс: охват {health.data.pulse_coverage}% · n={health.data.pulse_sample_size}. При выборке меньше 5 человек показатель скрывается.
        </p>
      </Card>

      {!health.data.pulse_suppressed && health.data.vector_dimensions.length > 0 && (
        <section>
          <div style={{ marginBottom: "0.55rem" }}><h3 style={{ margin: 0 }}>Из чего состоит Пульс</h3><p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "0.74rem" }}>Только агрегированные текущие состояния. Не черты личности и не оценка человека.</p></div>
          <div style={{ display: "grid", gap: "0.5rem" }}>
            {health.data.vector_dimensions.map((item) => (
              <Card key={item.key} style={{ padding: "0.75rem 0.85rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "baseline" }}><strong>{item.label}</strong><strong>{item.value}{item.delta === null ? "" : ` ${item.delta > 0 ? "↑" : item.delta < 0 ? "↓" : "→"}`}</strong></div>
                <div style={{ height: 6, borderRadius: 999, background: "var(--era-ring-track)", overflow: "hidden", marginTop: 8 }}><div style={{ width: `${Math.max(0, Math.min(100, item.value))}%`, height: "100%", background: "linear-gradient(90deg,var(--era-red),var(--era-gold-ink))" }} /></div>
              </Card>
            ))}
          </div>
        </section>
      )}

      {health.data.risks.length > 0 && (
        <section>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "end", marginBottom: "0.55rem" }}><h3 style={{ margin: 0 }}>Сигналы внимания</h3><StatusBadge label={`${health.data.risks.length}`} tone="red" /></div>
          <div style={{ display: "grid", gap: "0.5rem" }}>{health.data.risks.map((risk, index) => <Card key={`${risk}-${index}`} style={{ padding: "0.75rem 0.85rem", borderLeft: "3px solid var(--era-red)" }}><span style={{ fontSize: "0.8rem", lineHeight: 1.45 }}>{risk}</span></Card>)}</div>
        </section>
      )}

      <section>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "end", marginBottom: "0.55rem" }}>
          <div><p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Реальные данные платформы</p><h3 style={{ margin: "0.15rem 0 0" }}>Показатели здоровья</h3></div>
          <StatusBadge label={`${health.data.metrics.length} метрик`} tone="gold" />
        </div>
        {groupedMetrics.map(([category, metrics]) => (
          <div key={category} style={{ marginBottom: "0.8rem" }}>
            <strong style={{ display: "block", marginBottom: "0.45rem", color: "var(--era-text-muted)", fontSize: "0.72rem", textTransform: "uppercase" }}>{category}</strong>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: "0.5rem" }}>{metrics.map((metric) => <MetricCard key={metric.key} metric={metric} />)}</div>
          </div>
        ))}
        <button type="button" onClick={() => setShowAllMetrics((value) => !value)} style={{ width: "100%" }}>{showAllMetrics ? "Скрыть дополнительные" : `Показать все ${health.data.metrics.length} показателей`}</button>
      </section>

      <section>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "end", marginBottom: "0.55rem" }}><div><p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Эта неделя</p><h3 style={{ margin: "0.15rem 0 0" }}>Что делать дальше</h3></div><StatusBadge label={`${efficiency.data.recommendations.length} действий`} tone="violet" /></div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
          {efficiency.data.recommendations.map((item, index) => (
            <Card key={`${item.title}-${index}`} style={{ padding: "0.85rem 0.9rem" }}><div style={{ display: "flex", justifyContent: "space-between", gap: "0.65rem", alignItems: "flex-start" }}><strong style={{ fontSize: "0.95rem" }}>{item.title}</strong><StatusBadge label={priorityLabel(item.priority)} tone={priorityTone(item.priority)} /></div><p style={{ margin: "0.45rem 0 0", color: "var(--era-text-muted)", fontSize: "0.78rem", lineHeight: 1.45 }}>{item.reason}</p><p style={{ margin: "0.5rem 0 0", fontSize: "0.83rem", lineHeight: 1.45 }}><strong>→ {item.action}</strong></p></Card>
          ))}
        </div>
      </section>

      <section>
        <div style={{ marginBottom: "0.55rem" }}><p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Данные по объектам</p><h3 style={{ margin: "0.15rem 0 0" }}>Открыть или выгрузить</h3></div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
          {(Object.keys(SECTION_META) as AnalyticsDetailSection[]).map((section) => {
            const meta = SECTION_META[section];
            return (
              <Card key={section} style={{ padding: "0.8rem 0.85rem", borderLeft: `3px solid ${meta.accent}` }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "0.75rem", alignItems: "center" }}>
                  <button type="button" onClick={() => setSelectedSection(section)} style={{ border: 0, background: "transparent", padding: 0, textAlign: "left", color: "inherit", minHeight: 0 }}><strong style={{ display: "block", fontFamily: "var(--era-font-display)", fontSize: "1.45rem" }}>{analytics.data[meta.value]}</strong><strong style={{ display: "block", marginTop: "0.1rem" }}>{meta.label}</strong><span style={{ display: "block", marginTop: "0.18rem", color: "var(--era-text-muted)", fontSize: "0.72rem" }}>{meta.description} →</span></button>
                  <button type="button" disabled={downloadingSection !== null} onClick={() => void handleSectionDownload(section)} style={{ padding: "0.5rem 0.65rem", minHeight: "2.4rem" }}>{downloadingSection === section ? "…" : "↓ XLSX"}</button>
                </div>
              </Card>
            );
          })}
        </div>
      </section>

      <div style={{ display: "grid", gap: "0.55rem" }}>
        <button type="button" className="era-btn-primary" disabled={downloadingSection !== null} onClick={() => void handleHealthReport()} style={{ width: "100%", minHeight: "3.2rem" }}>{downloadingSection === "health" ? "Собираем здоровье…" : "↓ Здоровье организации · XLSX"}</button>
        <button type="button" disabled={downloadingSection !== null} onClick={() => void handleFullReport()} style={{ width: "100%", minHeight: "3.2rem" }}>{downloadingSection === "all" ? "Собираем отчёт…" : "↓ Полный отчёт ЭРА · XLSX"}</button>
      </div>

      <Card style={{ padding: "0.8rem 0.9rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "center" }}><div><strong>{dashboard.data.attention_total > 0 ? "Есть решения на очереди" : "Очередь чистая"}</strong><p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "0.76rem" }}>{dashboard.data.attention_total > 0 ? `${dashboard.data.attention_total} записей требуют решения. Они собраны в «Обзоре».` : "Ничего не ждёт проверки или ответа."}</p></div><strong style={{ fontFamily: "var(--era-font-display)", fontSize: "1.5rem" }}>{dashboard.data.attention_total}</strong></div>
      </Card>

      <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.68rem", lineHeight: 1.45 }}>{health.data.data_note}</p>
    </div>
  );
}
