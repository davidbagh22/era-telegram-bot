import { useCallback, useState } from "react";
import { fetchAdminAnalyticsDetails, type AnalyticsDetailSection } from "../../api/adminAnalytics";
import { downloadAnalyticsExcel, fetchAdminAnalyticsSummary, fetchAdminDashboard } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { MetricCard, type MetricTone } from "../../components/MetricCard";
import { StatusBadge } from "../../components/StatusBadge";
import { useToast } from "../../components/Toast";
import { useAsync } from "../../hooks/useAsync";
import type { AnalyticsExcelSection, AnalyticsSummary } from "../../types/admin";

const EXCEL_SECTIONS: { value: AnalyticsExcelSection; label: string }[] = [
  { value: "all", label: "Всё" },
  { value: "users", label: "Участники" },
  { value: "departments", label: "Департаменты" },
  { value: "events", label: "Мероприятия" },
  { value: "projects", label: "Проекты" },
];

const SECTION_META: Record<
  AnalyticsDetailSection,
  { label: string; description: string; tone: MetricTone; value: keyof AnalyticsSummary }
> = {
  users: {
    label: "Участники",
    description: "Все существующие записи участников",
    tone: "violet",
    value: "total_users",
  },
  events: {
    label: "Мероприятия",
    description: "События, которые уже есть в базе ЭРА",
    tone: "red",
    value: "events",
  },
  projects: {
    label: "Проекты",
    description: "Все существующие проектные записи",
    tone: "gold",
    value: "projects",
  },
  contacts: {
    label: "Организации",
    description: "Активная партнёрская база",
    tone: "magenta",
    value: "contacts",
  },
  goals: {
    label: "Цели",
    description: "Действующие и завершённые цели",
    tone: "violet",
    value: "goals",
  },
};

const STATUS_LABELS: Record<string, string> = {
  approved: "Одобрено",
  pending: "Ожидает",
  needs_info: "Нужны данные",
  rejected: "Отклонено",
  draft: "Черновик",
  published: "Опубликовано",
  active: "Активно",
  in_progress: "В работе",
  completed: "Завершено",
  done: "Готово",
};

function DetailView({ section, onBack }: { section: AnalyticsDetailSection; onBack: () => void }) {
  const state = useAsync(() => fetchAdminAnalyticsDetails(section), [section]);
  const meta = SECTION_META[section];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
      <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>
        ← К показателям
      </button>
      <div>
        <p
          style={{
            margin: "0 0 0.2rem",
            color: "var(--era-text-muted)",
            fontSize: "var(--era-text-xs)",
            fontWeight: 800,
            textTransform: "uppercase",
          }}
        >
          Реальные данные
        </p>
        <h2 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>{meta.label}</h2>
        <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)" }}>{meta.description}</p>
      </div>

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить записи." />}
      {state.status === "ready" && (
        <>
          <Card style={{ padding: "0.75rem 0.9rem", background: "var(--era-surface-2)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.75rem" }}>
              <strong>Найдено</strong>
              <strong style={{ fontFamily: "var(--era-font-display)", fontSize: "1.45rem" }}>{state.data.total}</strong>
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
                    {item.status && (
                      <StatusBadge label={STATUS_LABELS[item.status] ?? item.status} tone="neutral" />
                    )}
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
  const [selectedSection, setSelectedSection] = useState<AnalyticsDetailSection | null>(null);
  const [showExport, setShowExport] = useState(false);
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

  if (selectedSection) {
    return <DetailView section={selectedSection} onBack={() => setSelectedSection(null)} />;
  }

  if (dashboard.status === "loading" || analytics.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }
  if (dashboard.status === "error" || analytics.status === "error") {
    return <EmptyState text="Не удалось загрузить аналитику." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <Card gradient style={{ overflow: "hidden" }}>
        <p style={{ margin: "0 0 0.25rem", color: "rgba(255,255,255,0.72)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
          Контроль
        </p>
        <h2 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>Данные ЭРА</h2>
        <p style={{ margin: "0.5rem 0 0", color: "rgba(255,255,255,0.84)", lineHeight: 1.45 }}>
          Здесь нет декоративных цифр. Нажмите на показатель — откроются записи, из которых он посчитан.
        </p>
      </Card>

      <section>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.55rem" }}>
          {(Object.keys(SECTION_META) as AnalyticsDetailSection[]).map((section) => {
            const meta = SECTION_META[section];
            return (
              <MetricCard
                key={section}
                label={meta.label}
                value={analytics.data[meta.value]}
                tone={meta.tone}
                onClick={() => setSelectedSection(section)}
              />
            );
          })}
        </div>
      </section>

      <Card style={{ padding: "0.85rem 0.95rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "center" }}>
          <div>
            <strong>{dashboard.data.attention_total > 0 ? "Есть решения на очереди" : "Очередь чистая"}</strong>
            <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "0.78rem" }}>
              {dashboard.data.attention_total > 0
                ? `${dashboard.data.attention_total} записей требуют решения. Они собраны в «Обзоре».`
                : "Ничего не ждёт проверки или ответа."}
            </p>
          </div>
          <strong style={{ fontFamily: "var(--era-font-display)", fontSize: "1.5rem" }}>{dashboard.data.attention_total}</strong>
        </div>
      </Card>

      <section>
        <button
          type="button"
          onClick={() => setShowExport((current) => !current)}
          style={{ width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center" }}
        >
          <span>Экспорт Excel</span>
          <span>{showExport ? "−" : "+"}</span>
        </button>
        {showExport && (
          <Card style={{ marginTop: "0.55rem" }}>
            <p style={{ margin: "0 0 0.65rem", color: "var(--era-text-muted)", fontSize: "0.8rem" }}>
              Выберите, какие данные выгрузить.
            </p>
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
        )}
      </section>
    </div>
  );
}
