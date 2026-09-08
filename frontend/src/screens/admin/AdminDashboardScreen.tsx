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

// These are the metrics an administrator should be able to read in one glance.
// The complete metric set is preserved below in compact category drill-downs.
const EXECUTIVE_KEYS = [
  "approved",
  "active_30d",
  "new_30d",
  "retention_30d",
  "growth_conversion",
  "attendance_rate",
  "active_projects",
  "overdue_tasks",
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

function MiniRing({
  score,
  size,
  accent,
  showValue = true,
}: {
  score: number | null;
  size: number;
  accent: string;
  showValue?: boolean;
}) {
  const safeScore = Math.max(0, Math.min(100, score ?? 0));
  return (
    <div
      aria-hidden={!showValue}
      style={{
        width: size,
        height: size,
        flexShrink: 0,
        borderRadius: "50%",
        padding: Math.max(3, Math.round(size * 0.065)),
        background:
          score === null
            ? "var(--era-ring-track)"
            : `conic-gradient(${accent} 0 ${safeScore}%, var(--era-ring-track) ${safeScore}% 100%)`,
      }}
    >
      <div
        style={{
          width: "100%",
          height: "100%",
          borderRadius: "50%",
          background: "var(--era-surface)",
          display: "grid",
          placeItems: "center",
        }}
      >
        {showValue && (
          <strong
            style={{
              fontFamily: "var(--era-font-display)",
              fontSize: size * 0.29,
              lineHeight: 1,
            }}
          >
            {score ?? "—"}
          </strong>
        )}
      </div>
    </div>
  );
}

function HeroScore({ score, label, sublabel }: { score: number | null; label: string; sublabel: string }) {
  const accent = score === null ? "var(--era-text-muted)" : scoreTone(score);
  return (
    <div
      aria-label={`${label}: ${score ?? "нет данных"}${score === null ? "" : " из 100"}`}
      style={{ display: "grid", gridTemplateColumns: "72px 1fr", alignItems: "center", gap: "0.7rem" }}
    >
      <MiniRing score={score} size={72} accent={accent} />
      <div style={{ minWidth: 0 }}>
        <strong style={{ display: "block", fontSize: "0.95rem" }}>{label}</strong>
        <span style={{ display: "block", marginTop: 3, color: "var(--era-text-muted)", fontSize: "0.7rem", lineHeight: 1.35 }}>
          {sublabel}
        </span>
      </div>
    </div>
  );
}

function ScoreLine({ score }: { score: number }) {
  const safeScore = Math.max(0, Math.min(100, score));
  return (
    <div style={{ height: 4, borderRadius: 999, background: "var(--era-ring-track)", overflow: "hidden" }}>
      <div
        style={{
          width: `${safeScore}%`,
          height: "100%",
          borderRadius: 999,
          background: scoreTone(score),
          transition: "width .25s ease",
        }}
      />
    </div>
  );
}

function ExecutiveMetric({ metric }: { metric: HealthMetric }) {
  return (
    <div
      style={{
        minWidth: 0,
        padding: "0.65rem 0.7rem",
        border: "1px solid var(--era-border)",
        borderRadius: "calc(var(--era-radius-card) * .72)",
        background: "var(--era-surface-2)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", minHeight: 38 }}>
        {metric.score !== null && <MiniRing score={metric.score} size={36} accent={scoreTone(metric.score)} />}
        <strong
          style={{
            display: "block",
            fontFamily: "var(--era-font-display)",
            fontSize: metric.score === null ? "1.45rem" : "1.05rem",
            lineHeight: 1.05,
          }}
        >
          {metric.display}
        </strong>
      </div>
      <span style={{ display: "block", marginTop: "0.4rem", fontSize: "0.72rem", fontWeight: 800, lineHeight: 1.25 }}>
        {metric.label}
      </span>
    </div>
  );
}

function MetricRow({ metric }: { metric: HealthMetric }) {
  return (
    <div style={{ padding: "0.62rem 0", borderTop: "1px solid var(--era-border)" }}>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: "0.7rem", alignItems: "baseline" }}>
        <span style={{ minWidth: 0, fontSize: "0.78rem", fontWeight: 750, lineHeight: 1.25 }}>{metric.label}</span>
        <strong style={{ fontFamily: "var(--era-font-display)", fontSize: "1rem", whiteSpace: "nowrap" }}>{metric.display}</strong>
      </div>
      {metric.score !== null && (
        <div style={{ marginTop: "0.38rem" }}>
          <ScoreLine score={metric.score} />
        </div>
      )}
      {metric.note && (
        <span style={{ display: "block", marginTop: "0.28rem", color: "var(--era-text-muted)", fontSize: "0.63rem", lineHeight: 1.3 }}>
          {metric.note}
        </span>
      )}
    </div>
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
  const mediaAnalytics = useAsync(() => fetchMediaAnalytics(), []);
  const [selectedSection, setSelectedSection] = useState<AnalyticsDetailSection | null>(null);
  const [downloadingSection, setDownloadingSection] = useState<AnalyticsDetailSection | "all" | "health" | null>(null);
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(() => new Set());
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

  const executiveMetrics = useMemo(() => {
    if (health.status !== "ready") return [] as HealthMetric[];
    const byKey = new Map(health.data.metrics.map((metric) => [metric.key, metric]));
    return EXECUTIVE_KEYS
      .map((key) => byKey.get(key))
      .filter((metric): metric is HealthMetric => metric !== undefined)
      .slice(0, 8);
  }, [health]);

  const groupedMetrics = useMemo(() => {
    if (health.status !== "ready") return [] as { category: string; metrics: HealthMetric[]; avgScore: number | null }[];
    const groups = new Map<string, HealthMetric[]>();
    health.data.metrics.forEach((metric) => groups.set(metric.category, [...(groups.get(metric.category) ?? []), metric]));
    return Array.from(groups.entries()).map(([category, metrics]) => {
      const scored = metrics.map((metric) => metric.score).filter((score): score is number => score !== null);
      const avgScore = scored.length ? Math.round(scored.reduce((sum, score) => sum + score, 0) / scored.length) : null;
      return { category, metrics, avgScore };
    });
  }, [health]);

  const toggleCategory = (category: string) => {
    setExpandedCategories((current) => {
      const next = new Set(current);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      return next;
    });
  };

  if (selectedSection) return <DetailView section={selectedSection} onBack={() => setSelectedSection(null)} />;

  // The executive picture should not wait for secondary admin/export/media requests.
  if (efficiency.status === "loading" || health.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Собираем главное по ЭРА…</p>;
  }
  if (efficiency.status === "error" || health.status === "error") {
    return <EmptyState text="Не удалось загрузить ключевую аналитику. Данные не подменяются — попробуйте ещё раз." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
      <Card style={{ padding: "0.95rem", background: "radial-gradient(circle at 95% 0%, rgba(99,44,255,.14), transparent 44%), var(--era-surface)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.7rem" }}>
          <div>
            <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Админ · сейчас</p>
            <h2 style={{ margin: "0.15rem 0 0", fontSize: "var(--era-text-2xl)" }}>ЭРА одним взглядом</h2>
          </div>
          <StatusBadge label={health.data.period_label} tone="violet" />
        </div>
        <div style={{ display: "grid", gap: "0.7rem", marginTop: "0.8rem" }}>
          <HeroScore score={efficiency.data.score} label="Эффективность" sublabel={efficiency.data.label} />
          <div style={{ height: 1, background: "var(--era-border)" }} />
          <HeroScore
            score={health.data.pulse_suppressed ? null : health.data.pulse}
            label="Пульс сообщества"
            sublabel={health.data.pulse_suppressed ? "Недостаточно данных" : health.data.pulse_label}
          />
        </div>
        <p style={{ margin: "0.65rem 0 0", color: "var(--era-text-muted)", fontSize: "0.65rem" }}>
          Пульс: охват {health.data.pulse_coverage}% · n={health.data.pulse_sample_size}. При выборке меньше 5 человек показатель скрывается.
        </p>
      </Card>

      <section>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "end", gap: "0.75rem", marginBottom: "0.45rem" }}>
          <div>
            <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>8 ключевых</p>
            <h3 style={{ margin: "0.1rem 0 0" }}>Главное</h3>
          </div>
          <span style={{ color: "var(--era-text-muted)", fontSize: "0.68rem" }}>без лишнего</span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: "0.45rem" }}>
          {executiveMetrics.map((metric) => <ExecutiveMetric key={metric.key} metric={metric} />)}
        </div>
      </section>

      {health.data.risks.length > 0 && (
        <Card style={{ padding: "0.8rem 0.85rem", borderLeft: "3px solid var(--era-red)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.7rem" }}>
            <strong>Требует внимания</strong>
            <StatusBadge label={`${health.data.risks.length}`} tone="red" />
          </div>
          <div style={{ marginTop: "0.45rem", display: "grid", gap: "0.35rem" }}>
            {health.data.risks.map((risk, index) => (
              <div key={`${risk}-${index}`} style={{ display: "grid", gridTemplateColumns: "8px 1fr", gap: "0.45rem", alignItems: "start" }}>
                <span style={{ width: 6, height: 6, marginTop: 6, borderRadius: "50%", background: "var(--era-red)" }} />
                <span style={{ fontSize: "0.75rem", lineHeight: 1.38 }}>{risk}</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {!health.data.pulse_suppressed && health.data.vector_dimensions.length > 0 && (
        <section>
          <div style={{ marginBottom: "0.45rem" }}>
            <h3 style={{ margin: 0 }}>Пульс по направлениям</h3>
            <p style={{ margin: "0.15rem 0 0", color: "var(--era-text-muted)", fontSize: "0.68rem" }}>Пять состояний — одной линией на каждое.</p>
          </div>
          <Card style={{ padding: "0.2rem 0.85rem" }}>
            {health.data.vector_dimensions.map((item, index) => (
              <div key={item.key} style={{ padding: "0.65rem 0", borderTop: index === 0 ? 0 : "1px solid var(--era-border)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.7rem", alignItems: "baseline" }}>
                  <strong style={{ fontSize: "0.76rem" }}>{item.label}</strong>
                  <strong style={{ fontFamily: "var(--era-font-display)", fontSize: "0.95rem" }}>
                    {item.value}{item.delta === null ? "" : ` ${item.delta > 0 ? "↑" : item.delta < 0 ? "↓" : "→"}`}
                  </strong>
                </div>
                <div style={{ marginTop: "0.35rem" }}><ScoreLine score={item.value} /></div>
              </div>
            ))}
          </Card>
        </section>
      )}

      <section>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "end", gap: "0.75rem", marginBottom: "0.45rem" }}>
          <div>
            <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Ничего не удалено</p>
            <h3 style={{ margin: "0.1rem 0 0" }}>Все показатели</h3>
          </div>
          <StatusBadge label={`${health.data.metrics.length}`} tone="gold" />
        </div>
        <p style={{ margin: "0 0 0.45rem", color: "var(--era-text-muted)", fontSize: "0.68rem", lineHeight: 1.35 }}>
          Категории свёрнуты. Нажмите на нужную — внутри все показатели и пояснения.
        </p>
        <div style={{ display: "grid", gap: "0.45rem" }}>
          {groupedMetrics.map(({ category, metrics, avgScore }) => {
            const expanded = expandedCategories.has(category);
            return (
              <Card key={category} style={{ padding: "0.2rem 0.8rem" }}>
                <button
                  type="button"
                  onClick={() => toggleCategory(category)}
                  aria-expanded={expanded}
                  style={{
                    width: "100%",
                    minHeight: 52,
                    padding: "0.45rem 0",
                    border: 0,
                    background: "transparent",
                    color: "inherit",
                    display: "grid",
                    gridTemplateColumns: avgScore === null ? "1fr auto" : "34px 1fr auto",
                    gap: "0.55rem",
                    alignItems: "center",
                    textAlign: "left",
                  }}
                >
                  {avgScore !== null && <MiniRing score={avgScore} size={32} accent={scoreTone(avgScore)} showValue={false} />}
                  <div style={{ minWidth: 0 }}>
                    <strong style={{ display: "block", fontSize: "0.8rem", lineHeight: 1.2 }}>{category}</strong>
                    <span style={{ display: "block", marginTop: 2, color: "var(--era-text-muted)", fontSize: "0.64rem" }}>
                      {metrics.length} показателей{avgScore === null ? "" : ` · индекс ${avgScore}`}
                    </span>
                  </div>
                  <span style={{ color: "var(--era-text-muted)", fontSize: "1rem", transform: expanded ? "rotate(180deg)" : "none", transition: "transform .2s ease" }}>⌄</span>
                </button>
                {expanded && (
                  <div style={{ paddingBottom: "0.2rem" }}>
                    {metrics.map((metric) => <MetricRow key={metric.key} metric={metric} />)}
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      </section>

      {mediaAnalytics.status === "ready" && (
        <section>
          <div style={{ marginBottom: "0.45rem" }}>
            <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Подразделение</p>
            <h3 style={{ margin: "0.1rem 0 0" }}>Медиа</h3>
          </div>
          <Card style={{ padding: "0.7rem 0.8rem" }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: "0.65rem" }}>
              <div><strong style={{ display: "block", fontFamily: "var(--era-font-display)", fontSize: "1.25rem" }}>{mediaAnalytics.data.published}</strong><span style={{ fontSize: "0.68rem" }}>публикаций</span></div>
              <div><strong style={{ display: "block", fontFamily: "var(--era-font-display)", fontSize: "1.25rem" }}>{mediaAnalytics.data.chat_messages_period}</strong><span style={{ fontSize: "0.68rem" }}>сообщений / 30 дней</span></div>
              <div><strong style={{ display: "block", fontFamily: "var(--era-font-display)", fontSize: "1.25rem" }}>{mediaAnalytics.data.tasks_completed}/{mediaAnalytics.data.tasks_created}</strong><span style={{ fontSize: "0.68rem" }}>задач выполнено</span></div>
              <div><strong style={{ display: "block", fontFamily: "var(--era-font-display)", fontSize: "1.25rem" }}>{mediaAnalytics.data.on_time_rate == null ? "—" : `${mediaAnalytics.data.on_time_rate}%`}</strong><span style={{ fontSize: "0.68rem" }}>вышло вовремя</span></div>
            </div>
          </Card>
        </section>
      )}

      <section>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "end", gap: "0.75rem", marginBottom: "0.45rem" }}>
          <div><p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Эта неделя</p><h3 style={{ margin: "0.1rem 0 0" }}>Что делать дальше</h3></div>
          <StatusBadge label={`${efficiency.data.recommendations.length}`} tone="violet" />
        </div>
        <div style={{ display: "grid", gap: "0.45rem" }}>
          {efficiency.data.recommendations.map((item, index) => (
            <Card key={`${item.title}-${index}`} style={{ padding: "0.75rem 0.8rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "0.55rem", alignItems: "flex-start" }}>
                <strong style={{ fontSize: "0.86rem" }}>{item.title}</strong>
                <StatusBadge label={priorityLabel(item.priority)} tone={priorityTone(item.priority)} />
              </div>
              <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "0.7rem", lineHeight: 1.4 }}>{item.reason}</p>
              <p style={{ margin: "0.4rem 0 0", fontSize: "0.75rem", lineHeight: 1.4 }}><strong>→ {item.action}</strong></p>
            </Card>
          ))}
        </div>
      </section>

      {analytics.status === "ready" && (
        <section>
          <div style={{ marginBottom: "0.45rem" }}><p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Данные по объектам</p><h3 style={{ margin: "0.1rem 0 0" }}>Открыть или выгрузить</h3></div>
          <div style={{ display: "grid", gap: "0.45rem" }}>
            {(Object.keys(SECTION_META) as AnalyticsDetailSection[]).map((section) => {
              const meta = SECTION_META[section];
              return (
                <Card key={section} style={{ padding: "0.7rem 0.8rem", borderLeft: `3px solid ${meta.accent}` }}>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "0.65rem", alignItems: "center" }}>
                    <button type="button" onClick={() => setSelectedSection(section)} style={{ border: 0, background: "transparent", padding: 0, textAlign: "left", color: "inherit", minHeight: 0 }}>
                      <strong style={{ fontFamily: "var(--era-font-display)", fontSize: "1.25rem" }}>{analytics.data[meta.value]}</strong>
                      <span style={{ marginLeft: "0.45rem", fontWeight: 800, fontSize: "0.78rem" }}>{meta.label}</span>
                    </button>
                    <button type="button" disabled={downloadingSection !== null} onClick={() => void handleSectionDownload(section)} style={{ padding: "0.45rem 0.6rem", minHeight: "2.2rem" }}>{downloadingSection === section ? "…" : "↓"}</button>
                  </div>
                </Card>
              );
            })}
          </div>
        </section>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.45rem" }}>
        <button type="button" className="era-btn-primary" disabled={downloadingSection !== null} onClick={() => void handleHealthReport()} style={{ minHeight: "2.8rem", fontSize: "0.72rem" }}>{downloadingSection === "health" ? "…" : "↓ Здоровье"}</button>
        <button type="button" disabled={downloadingSection !== null} onClick={() => void handleFullReport()} style={{ minHeight: "2.8rem", fontSize: "0.72rem" }}>{downloadingSection === "all" ? "…" : "↓ Весь отчёт"}</button>
      </div>

      {dashboard.status === "ready" && (
        <Card style={{ padding: "0.7rem 0.8rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "center" }}>
            <div>
              <strong>{dashboard.data.attention_total > 0 ? "Есть решения на очереди" : "Очередь чистая"}</strong>
              <p style={{ margin: "0.15rem 0 0", color: "var(--era-text-muted)", fontSize: "0.68rem" }}>
                {dashboard.data.attention_total > 0 ? "Откройте «Обзор», чтобы разобрать очередь." : "Ничего не ждёт проверки или ответа."}
              </p>
            </div>
            <strong style={{ fontFamily: "var(--era-font-display)", fontSize: "1.4rem" }}>{dashboard.data.attention_total}</strong>
          </div>
        </Card>
      )}

      <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.62rem", lineHeight: 1.4 }}>{health.data.data_note}</p>
    </div>
  );
}
