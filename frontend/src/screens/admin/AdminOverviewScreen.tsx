import { fetchAdminDashboard, fetchRecentActivity } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { MetricCard, type MetricTone } from "../../components/MetricCard";
import { useAsync } from "../../hooks/useAsync";

const TONE_CYCLE: MetricTone[] = ["violet", "red", "gold", "magenta"];

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
  return `${Math.round(hours / 24)} дн назад`;
}

export function AdminOverviewScreen() {
  const dashboard = useAsync(() => fetchAdminDashboard(), []);
  const activity = useAsync(() => fetchRecentActivity(), []);

  if (dashboard.status === "loading") return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  if (dashboard.status === "error") return <EmptyState text="Не удалось загрузить обзор." />;

  const { metrics, attention_total } = dashboard.data;
  const attentionItems = ATTENTION_ORDER.map((key) => ({ key, label: ATTENTION_LABELS[key], value: metrics[key] ?? 0 })).filter(
    (item) => item.value > 0,
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div>
        <p style={{ margin: "0 0 0.25rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Управление ЭРА</p>
        <h1 style={{ margin: 0, fontSize: "var(--era-text-3xl)" }}>Обзор</h1>
        <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)" }}>Решения, которые требуют внимания команды сейчас.</p>
      </div>

      <section>
        <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: "0 0 0.5rem" }}>Требует внимания</h2>
        {attention_total === 0 ? (
          <Card style={{ background: "var(--era-tint-violet)", border: "none", textAlign: "center" }}>
            <div style={{ fontSize: "1.75rem" }}>✨</div>
            <strong style={{ color: "var(--era-violet)" }}>Всё спокойно</strong>
            <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>Нет задач, требующих решения</p>
          </Card>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {attentionItems.map((item, index) => {
              const tone = TONE_CYCLE[index % TONE_CYCLE.length];
              return (
                <Card key={item.key} style={{ borderLeft: `3px solid var(--era-${tone})`, borderRadius: "var(--era-radius-card)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span>{item.label}</span>
                    <strong style={{ fontFamily: "var(--era-font-display)", fontSize: "1.125rem", color: `var(--era-${tone})` }}>{item.value}</strong>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </section>

      <section>
        <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: "0 0 0.5rem" }}>Пульс сообщества</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.5rem" }}>
          {Object.keys(KPI_LABELS).map((key, index) => (
            <MetricCard key={key} label={KPI_LABELS[key]} value={metrics[key] ?? 0} tone={TONE_CYCLE[index % TONE_CYCLE.length]} />
          ))}
        </div>
      </section>

      <section>
        <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: "0 0 0.5rem" }}>Последняя активность</h2>
        {activity.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
        {activity.status === "error" && <EmptyState text="Не удалось загрузить активность." />}
        {activity.status === "ready" && activity.data.length === 0 && <EmptyState text="Пока ничего не происходило." />}
        {activity.status === "ready" && activity.data.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
            {activity.data.map((entry, index) => (
              <div key={entry.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", padding: "0.5rem 0", borderBottom: "1px solid var(--era-border)", fontSize: "0.8125rem" }}>
                <span style={{ display: "flex", alignItems: "center", gap: "0.5rem", minWidth: 0 }}>
                  <span aria-hidden="true" style={{ width: "0.4375rem", height: "0.4375rem", borderRadius: "50%", flexShrink: 0, background: `var(--era-${TONE_CYCLE[index % TONE_CYCLE.length]})` }} />
                  <span style={{ overflowWrap: "anywhere" }}>{entry.actor_name ? <strong>{entry.actor_name}</strong> : "Кто-то"} {entry.summary}</span>
                </span>
                <span style={{ color: "var(--era-text-muted)", whiteSpace: "nowrap", flexShrink: 0 }}>{timeAgo(entry.created_at)}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}