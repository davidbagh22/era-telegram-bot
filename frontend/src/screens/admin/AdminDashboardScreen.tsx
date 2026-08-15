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
    tone: "red",
    value: "total_users",
  },
  events: {
    label: "Мероприятия",
    description: "События, которые уже есть в базе ЭРА",
    tone: "magenta",
    value: "events",
  },
  projects: {
    label: "Проекты",
    description: "Все существующие проектные записи",
    tone: "red",
    value: "projects",
  },
  contacts: {
    label: "Организации",
    description: "Активная партнёрская база",
    tone: "gold",
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
      <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← К данным</button>
      <Card gradient style={{ position: "relative", overflow: "hidden" }}>
        <div aria-hidden="true" style={{ position: "absolute", right: -55, top: -70, width: 160, height: 160, borderRadius: "50%", border: "1px solid rgba(255,255,255,.22)" }} />
        <div style={{ position: "relative" }}>
          <p style={{ margin: "0 0 0.2rem", color: "rgba(255,255,255,.74)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Реальные записи</p>
          <h2 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>{meta.label}</h2>
          <p style={{ margin: "0.35rem 0 0", color: "rgba(255,255,255,.84)" }}>{meta.description}</p>
        </div>
      </Card>

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить записи." />}
      {state.status === "ready" && (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "0.25rem 0.1rem" }}>
            <span style={{ color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>Сейчас в базе</span>
            <strong style={{ fontFamily: "var(--era-font-display)", fontSize: "1.7rem", color: "var(--era-red)" }}>{state.data.total}</strong>
          </div>

          {state.data.items.length === 0 ? (
            <EmptyState text="Записей пока нет." />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {state.data.items.map((item, index) => (
                <Card key={`${section}-${item.id}`} style={{ padding: "0.8rem 0.9rem", borderLeft: index === 0 ? "3px solid var(--era-red)" : undefined }}>
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
  const [selectedSection, setSelectedSection] = useState<AnalyticsDetailSection | null>(null);
  const [showExport, setShowExport] = useState(false);
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

  if (selectedSection) return <DetailView section={selectedSection} onBack={() => setSelectedSection(null)} />;
  if (dashboard.status === "loading" || analytics.status === "loading") return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  if (dashboard.status === "error" || analytics.status === "error") return <EmptyState text="Не удалось загрузить аналитику." />;

  const userMeta = SECTION_META.users;
  const secondarySections = (Object.keys(SECTION_META) as AnalyticsDetailSection[]).filter((section) => section !== "users");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <Card gradient style={{ overflow: "hidden", position: "relative", minHeight: 170 }}>
        <div aria-hidden="true" style={{ position: "absolute", width: 210, height: 210, borderRadius: "50%", right: -90, top: -115, border: "1px solid rgba(255,255,255,.22)", boxShadow: "0 0 90px rgba(255,255,255,.09)" }} />
        <div style={{ position: "relative" }}>
          <p style={{ margin: "0 0 0.25rem", color: "rgba(255,255,255,0.74)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Контроль · live</p>
          <h2 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>Живые данные ЭРА</h2>
          <p style={{ margin: "0.5rem 0 0", color: "rgba(255,255,255,0.86)", lineHeight: 1.45, maxWidth: 330 }}>
            Каждая цифра — вход в реальные записи. Нажмите показатель и увидите именно тех людей, проекты или события, из которых он посчитан.
          </p>
        </div>
      </Card>

      <button
        type="button"
        onClick={() => setSelectedSection("users")}
        style={{
          minHeight: 112,
          width: "100%",
          padding: "0.95rem 1rem",
          borderRadius: "var(--era-radius-card)",
          textAlign: "left",
          background: "radial-gradient(80% 160% at 100% 0%, rgba(255,255,255,.13), transparent 55%), linear-gradient(135deg, rgba(255,32,56,.24), rgba(255,37,111,.08)), var(--era-surface)",
          border: "1px solid rgba(255,32,56,.28)",
          boxShadow: "var(--era-shadow-soft)",
        }}
      >
        <span style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "flex-end" }}>
          <span>
            <span style={{ display: "block", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Главный показатель</span>
            <strong style={{ display: "block", marginTop: "0.25rem", fontSize: "var(--era-text-xl)" }}>{userMeta.label}</strong>
            <span style={{ display: "block", marginTop: "0.3rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>Нажмите → открыть список</span>
          </span>
          <strong style={{ fontFamily: "var(--era-font-display)", fontSize: "2.65rem", lineHeight: 0.9, color: "#fff" }}>{analytics.data[userMeta.value]}</strong>
        </span>
      </button>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.55rem" }}>
        {secondarySections.map((section) => {
          const meta = SECTION_META[section];
          return <MetricCard key={section} label={meta.label} value={analytics.data[meta.value]} tone={meta.tone} onClick={() => setSelectedSection(section)} />;
        })}
      </div>

      <Card style={{ padding: "0.9rem 1rem", borderColor: dashboard.data.attention_total > 0 ? "rgba(255,32,56,.28)" : "var(--era-border)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "center" }}>
          <div>
            <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Очередь решений</p>
            <strong style={{ display: "block", marginTop: "0.2rem" }}>{dashboard.data.attention_total > 0 ? "Нужно внимание" : "Всё обработано"}</strong>
            <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "0.78rem" }}>{dashboard.data.attention_total > 0 ? "Детали собраны на экране «Обзор»." : "Ничего не ждёт проверки или ответа."}</p>
          </div>
          <strong style={{ fontFamily: "var(--era-font-display)", fontSize: "1.85rem", color: dashboard.data.attention_total > 0 ? "var(--era-red)" : "var(--era-success)" }}>{dashboard.data.attention_total}</strong>
        </div>
      </Card>

      <section>
        <button type="button" onClick={() => setShowExport((current) => !current)} style={{ width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>📊 Выгрузить Excel</span><span>{showExport ? "−" : "+"}</span>
        </button>
        {showExport && (
          <Card style={{ marginTop: "0.55rem" }}>
            <p style={{ margin: "0 0 0.65rem", color: "var(--era-text-muted)", fontSize: "0.8rem" }}>Экспорт не смешан с аналитикой: выберите только то, что действительно нужно выгрузить.</p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
              {EXCEL_SECTIONS.map((section) => (
                <button key={section.value} type="button" disabled={downloadingSection !== null} onClick={() => handleDownload(section.value)}>
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
