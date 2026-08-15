import { useCallback, useState } from "react";
import {
  downloadAnalyticsSectionTable,
  downloadFullAnalyticsReport,
  fetchAdminAnalyticsDetails,
  fetchEraEfficiency,
  type AnalyticsDetailSection,
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
    accent: "#8b5cf6",
  },
  events: {
    label: "Мероприятия",
    description: "Все события ЭРА",
    value: "events",
    accent: "#ff335f",
  },
  projects: {
    label: "Проекты",
    description: "Инициативы и проектная воронка",
    value: "projects",
    accent: "#f4c15d",
  },
  contacts: {
    label: "Организации",
    description: "Партнёрская база",
    value: "contacts",
    accent: "#e73da8",
  },
  goals: {
    label: "Цели",
    description: "Цели организации и направлений",
    value: "goals",
    accent: "#6b5cff",
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

function DetailView({ section, onBack }: { section: AnalyticsDetailSection; onBack: () => void }) {
  const state = useAsync(() => fetchAdminAnalyticsDetails(section), [section]);
  const meta = SECTION_META[section];
  const toast = useToast();
  const [downloading, setDownloading] = useState(false);

  const downloadTable = async () => {
    setDownloading(true);
    try {
      saveBlob(await downloadAnalyticsSectionTable(section), `ERA_${section}.csv`);
    } catch {
      toast.show("Не удалось собрать таблицу.", "error");
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
      <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>
        ← Аналитика
      </button>

      <Card gradient>
        <p style={{ margin: 0, opacity: 0.72, fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
          Раздел аналитики
        </p>
        <h2 style={{ margin: "0.2rem 0 0", fontSize: "var(--era-text-2xl)" }}>{meta.label}</h2>
        <p style={{ margin: "0.35rem 0 0", opacity: 0.84 }}>{meta.description}</p>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
        <button type="button" disabled={downloading} onClick={() => void downloadTable()}>
          ↓ Таблица CSV
        </button>
        <button type="button" className="era-btn-primary" disabled={downloading} onClick={() => void downloadFull()}>
          ↓ Полный XLSX
        </button>
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

          {state.data.items.length === 0 ? (
            <EmptyState text="Записей пока нет." />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {state.data.items.map((item) => (
                <Card key={`${section}-${item.id}`} style={{ padding: "0.8rem 0.9rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "flex-start" }}>
                    <div style={{ minWidth: 0 }}>
                      <strong style={{ display: "block", overflowWrap: "anywhere" }}>{item.title}</strong>
                      {item.subtitle && (
                        <span style={{ display: "block", marginTop: "0.25rem", color: "var(--era-text-muted)", fontSize: "0.78rem", overflowWrap: "anywhere" }}>
                          {item.subtitle}
                        </span>
                      )}
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
  const [selectedSection, setSelectedSection] = useState<AnalyticsDetailSection | null>(null);
  const [downloadingSection, setDownloadingSection] = useState<AnalyticsDetailSection | "all" | null>(null);
  const toast = useToast();

  const handleSectionDownload = useCallback(
    async (section: AnalyticsDetailSection) => {
      setDownloadingSection(section);
      try {
        saveBlob(await downloadAnalyticsSectionTable(section), `ERA_${section}.csv`);
      } catch {
        toast.show("Не удалось собрать таблицу.", "error");
      } finally {
        setDownloadingSection(null);
      }
    },
    [toast],
  );

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

  if (selectedSection) {
    return <DetailView section={selectedSection} onBack={() => setSelectedSection(null)} />;
  }

  if (dashboard.status === "loading" || analytics.status === "loading" || efficiency.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Собираем аналитику ЭРА…</p>;
  }
  if (dashboard.status === "error" || analytics.status === "error" || efficiency.status === "error") {
    return <EmptyState text="Не удалось загрузить аналитику. Данные не подменяются — попробуйте ещё раз." />;
  }

  const score = efficiency.data.score;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
      <Card
        style={{
          padding: "1rem",
          overflow: "hidden",
          background: "radial-gradient(circle at 85% 0%, rgba(255,45,120,0.20), transparent 38%), radial-gradient(circle at 0% 100%, rgba(107,60,255,0.20), transparent 42%), var(--era-surface)",
        }}
      >
        <div style={{ display: "grid", gridTemplateColumns: "112px 1fr", gap: "0.9rem", alignItems: "center" }}>
          <div
            aria-label={`Эффективность ЭРА ${score} из 100`}
            style={{
              width: 108,
              height: 108,
              borderRadius: "50%",
              padding: 8,
              background: `conic-gradient(#ff2f8e 0 ${score}%, rgba(255,255,255,0.09) ${score}% 100%)`,
              boxShadow: "0 0 30px rgba(255,47,142,0.16)",
            }}
          >
            <div style={{ width: "100%", height: "100%", borderRadius: "50%", background: "var(--era-bg)", display: "grid", placeItems: "center", textAlign: "center" }}>
              <div>
                <strong style={{ display: "block", fontFamily: "var(--era-font-display)", fontSize: "1.85rem", lineHeight: 1 }}>{score}</strong>
                <span style={{ color: "var(--era-text-muted)", fontSize: "0.68rem", fontWeight: 800 }}>/ 100</span>
              </div>
            </div>
          </div>
          <div>
            <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
              Эффективность ЭРА
            </p>
            <h2 style={{ margin: "0.18rem 0 0", fontSize: "var(--era-text-xl)" }}>{efficiency.data.label}</h2>
            <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "0.78rem", lineHeight: 1.4 }}>
              {efficiency.data.period_label}
            </p>
          </div>
        </div>
        <p style={{ margin: "0.8rem 0 0", color: "var(--era-text-muted)", fontSize: "0.74rem", lineHeight: 1.4 }}>
          {efficiency.data.data_note}
        </p>
      </Card>

      <section>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "end", marginBottom: "0.55rem" }}>
          <div>
            <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Эта неделя</p>
            <h3 style={{ margin: "0.15rem 0 0" }}>Что делать дальше</h3>
          </div>
          <StatusBadge label={`${efficiency.data.recommendations.length} действий`} tone="violet" />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
          {efficiency.data.recommendations.map((item, index) => (
            <Card key={`${item.title}-${index}`} style={{ padding: "0.85rem 0.9rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "0.65rem", alignItems: "flex-start" }}>
                <strong style={{ fontSize: "0.95rem" }}>{item.title}</strong>
                <StatusBadge label={priorityLabel(item.priority)} tone={priorityTone(item.priority)} />
              </div>
              <p style={{ margin: "0.45rem 0 0", color: "var(--era-text-muted)", fontSize: "0.78rem", lineHeight: 1.45 }}>{item.reason}</p>
              <p style={{ margin: "0.5rem 0 0", fontSize: "0.83rem", lineHeight: 1.45 }}><strong>→ {item.action}</strong></p>
            </Card>
          ))}
        </div>
      </section>

      <section>
        <h3 style={{ margin: "0 0 0.55rem" }}>Пульс организации</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.5rem" }}>
          {efficiency.data.metrics.map((metric) => (
            <Card key={metric.key} style={{ padding: "0.75rem 0.8rem" }}>
              <strong style={{ display: "block", fontFamily: "var(--era-font-display)", fontSize: "1.35rem" }}>{metric.display}</strong>
              <span style={{ display: "block", marginTop: "0.18rem", fontWeight: 800, fontSize: "0.78rem" }}>{metric.label}</span>
              <span style={{ display: "block", marginTop: "0.22rem", color: "var(--era-text-muted)", fontSize: "0.7rem", lineHeight: 1.35 }}>{metric.note}</span>
            </Card>
          ))}
        </div>
      </section>

      <section>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "end", marginBottom: "0.55rem" }}>
          <div>
            <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Все данные</p>
            <h3 style={{ margin: "0.15rem 0 0" }}>Открыть или выгрузить</h3>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
          {(Object.keys(SECTION_META) as AnalyticsDetailSection[]).map((section) => {
            const meta = SECTION_META[section];
            return (
              <Card key={section} style={{ padding: "0.8rem 0.85rem", borderLeft: `3px solid ${meta.accent}` }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "0.75rem", alignItems: "center" }}>
                  <button
                    type="button"
                    onClick={() => setSelectedSection(section)}
                    style={{ border: 0, background: "transparent", padding: 0, textAlign: "left", color: "inherit", minHeight: 0 }}
                  >
                    <strong style={{ display: "block", fontFamily: "var(--era-font-display)", fontSize: "1.45rem" }}>{analytics.data[meta.value]}</strong>
                    <strong style={{ display: "block", marginTop: "0.1rem" }}>{meta.label}</strong>
                    <span style={{ display: "block", marginTop: "0.18rem", color: "var(--era-text-muted)", fontSize: "0.72rem" }}>{meta.description} →</span>
                  </button>
                  <button type="button" disabled={downloadingSection !== null} onClick={() => void handleSectionDownload(section)} style={{ padding: "0.5rem 0.65rem", minHeight: "2.4rem" }}>
                    {downloadingSection === section ? "…" : "↓ CSV"}
                  </button>
                </div>
              </Card>
            );
          })}
        </div>
      </section>

      <button type="button" className="era-btn-primary" disabled={downloadingSection !== null} onClick={() => void handleFullReport()} style={{ width: "100%", minHeight: "3.2rem" }}>
        {downloadingSection === "all" ? "Собираем отчёт…" : "↓ Полный отчёт ЭРА · XLSX"}
      </button>

      <Card style={{ padding: "0.8rem 0.9rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "center" }}>
          <div>
            <strong>{dashboard.data.attention_total > 0 ? "Есть решения на очереди" : "Очередь чистая"}</strong>
            <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "0.76rem" }}>
              {dashboard.data.attention_total > 0
                ? `${dashboard.data.attention_total} записей требуют решения. Они собраны в «Обзоре».`
                : "Ничего не ждёт проверки или ответа."}
            </p>
          </div>
          <strong style={{ fontFamily: "var(--era-font-display)", fontSize: "1.5rem" }}>{dashboard.data.attention_total}</strong>
        </div>
      </Card>
    </div>
  );
}
