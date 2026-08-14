import { useState } from "react";
import { fetchAdminDashboard, fetchRecentActivity } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { MetricCard, type MetricTone } from "../../components/MetricCard";
import { useAsync } from "../../hooks/useAsync";
import { AdminDashboardScreen } from "./AdminDashboardScreen";
import { AdminMaintenanceScreen } from "./AdminMaintenanceScreen";

// Reused for both the attention list's left accent bar and the KPI grid's
// tint — a light visual signature per item so the screen isn't a wall of
// identical white cards, without inventing new meaning per color (unlike
// HomeScreen's tones, none of these map to a fixed category here, so they
// just cycle for variety).
const TONE_CYCLE: MetricTone[] = ["violet", "red", "gold", "magenta"];

// "Что мне нужно сделать сейчас?", not "где находится функция?" — the
// 2026-08 Admin Mode redesign's Обзор tab. Replaces the old
// AdminDashboardScreen's role as the landing screen: that giant "0
// требует внимания" gradient hero (full width, shown even when there was
// genuinely nothing to review) is gone, along with the flat 12-tab row
// this used to sit under — see AdminScreen.tsx for the new grouping and
// docs/UI_DESIGN_SYSTEM.md for the full rationale.
//
// 2026-08 redesign brief section 34: "4 фиксированные группы, не 5" —
// the standalone Аналитика bottom-nav group is gone; AdminDashboardScreen
// (full metric breakdown + Excel export) is folded in below as a
// collapsible "Полная аналитика" section, same collapse pattern as
// Обслуживание further down. Collapsed by default so Обзор keeps its
// "what needs a decision right now" focus and doesn't fire the
// dashboard's own fetches on every Overview visit.
const ATTENTION_LABELS: Record<string, string> = {
  users_pending: "Новые заявки",
  projects_review: "Проекты на проверке",
  events_pending: "События на согласовании",
  task_results: "Итоги заданий",
  activity_results: "Активности после мероприятий",
  rewards: "Заявки на возможности",
  portfolio: "Портфолио на проверке",
  reports: "Отчёты",
  questions: "Вопросы",
  departments: "Заявки по направлениям",
};

const ATTENTION_ORDER = Object.keys(ATTENTION_LABELS);

const KPI_LABELS: Record<string, string> = {
  users_total: "Участников",
  projects_active: "Активные проекты",
  events_live: "Мероприятия в работе",
  leaders: "Лидеры и совет",
};

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "только что";
  if (minutes < 60) return `${minutes} мин назад`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} ч назад`;
  const days = Math.round(hours / 24);
  return `${days} дн назад`;
}

export function AdminOverviewScreen() {
  const dashboard = useAsync(() => fetchAdminDashboard(), []);
  const activity = useAsync(() => fetchRecentActivity(), []);
  const [analyticsOpen, setAnalyticsOpen] = useState(false);
  const [maintenanceOpen, setMaintenanceOpen] = useState(false);

  if (dashboard.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }
  if (dashboard.status === "error") {
    return <EmptyState text="Не удалось загрузить обзор." />;
  }

  const { metrics, attention_total } = dashboard.data;
  const attentionItems = ATTENTION_ORDER.map((key) => ({ key, label: ATTENTION_LABELS[key], value: metrics[key] ?? 0 })).filter(
    (item) => item.value > 0,
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <section>
        <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: "0 0 0.5rem" }}>
          Требует внимания
        </h2>
        {attention_total === 0 ? (
          <Card style={{ background: "var(--era-tint-violet)", border: "none", textAlign: "center" }}>
            <div style={{ fontSize: "1.75rem" }}>✨</div>
            <strong style={{ color: "var(--era-violet)" }}>Всё спокойно</strong>
            <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
              Нет задач, требующих решения
            </p>
          </Card>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {attentionItems.map((item, index) => {
              const tone = TONE_CYCLE[index % TONE_CYCLE.length];
              return (
                <Card key={item.key} style={{ borderLeft: `3px solid var(--era-${tone})`, borderRadius: "var(--era-radius-card)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span>{item.label}</span>
                    <strong
                      style={{
                        fontFamily: "var(--era-font-display)",
                        fontSize: "1.125rem",
                        color: `var(--era-${tone})`,
                      }}
                    >
                      {item.value}
                    </strong>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </section>

      <section>
        <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: "0 0 0.5rem" }}>
          Показатели
        </h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "0.5rem" }}>
          {Object.keys(KPI_LABELS).map((key, index) => (
            <MetricCard
              key={key}
              label={KPI_LABELS[key]}
              value={metrics[key] ?? 0}
              tone={TONE_CYCLE[index % TONE_CYCLE.length]}
            />
          ))}
        </div>
      </section>

      <section>
        <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: "0 0 0.5rem" }}>
          Последняя активность
        </h2>
        {activity.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
        {activity.status === "error" && <EmptyState text="Не удалось загрузить активность." />}
        {activity.status === "ready" && activity.data.length === 0 && (
          <EmptyState text="Пока ничего не происходило." />
        )}
        {activity.status === "ready" && activity.data.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
            {activity.data.map((entry, index) => (
              <div
                key={entry.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "0.5rem",
                  padding: "0.5rem 0",
                  borderBottom: "1px solid var(--era-border)",
                  fontSize: "0.8125rem",
                }}
              >
                <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <span
                    style={{
                      width: "0.4375rem",
                      height: "0.4375rem",
                      borderRadius: "50%",
                      flexShrink: 0,
                      background: `var(--era-${TONE_CYCLE[index % TONE_CYCLE.length]})`,
                    }}
                  />
                  {entry.actor_name ? <strong>{entry.actor_name}</strong> : "Кто-то"} {entry.summary}
                </span>
                <span style={{ color: "var(--era-text-muted)", whiteSpace: "nowrap" }}>
                  {timeAgo(entry.created_at)}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Full metric breakdown + Excel export (former standalone
       * Аналитика group) — collapsible, same pattern as Обслуживание
       * below, so Обзор's landing view stays focused on what needs a
       * decision right now. */}
      <section>
        <button
          type="button"
          onClick={() => setAnalyticsOpen((open) => !open)}
          style={{
            background: "none",
            border: "none",
            padding: 0,
            color: "var(--era-text-muted)",
            fontSize: "0.75rem",
            textDecoration: "underline",
            minHeight: "auto",
          }}
        >
          {analyticsOpen ? "Скрыть полную аналитику" : "Полная аналитика и Excel-выгрузка"}
        </button>
        {analyticsOpen && (
          <div style={{ marginTop: "0.75rem" }}>
            <AdminDashboardScreen />
          </div>
        )}
      </section>

      {/* Tucked away on purpose — this wipes test data and is gated
       * server-side to the ADMIN_IDS env var specifically (see
       * app/api/v1/admin.py's require_maintenance_access), not general
       * dashboard access, so it doesn't earn a spot in the main grouped
       * navigation. AdminMaintenanceScreen itself still shows its own
       * "недоступно" message to anyone who isn't in that list. */}
      <section>
        <button
          type="button"
          onClick={() => setMaintenanceOpen((open) => !open)}
          style={{
            background: "none",
            border: "none",
            padding: 0,
            color: "var(--era-text-muted)",
            fontSize: "0.75rem",
            textDecoration: "underline",
            minHeight: "auto",
          }}
        >
          {maintenanceOpen ? "Скрыть обслуживание" : "Обслуживание"}
        </button>
        {maintenanceOpen && (
          <div style={{ marginTop: "0.5rem" }}>
            <AdminMaintenanceScreen />
          </div>
        )}
      </section>
    </div>
  );
}
