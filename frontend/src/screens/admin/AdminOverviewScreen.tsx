import { useState } from "react";
import { fetchAdminDashboard } from "../../api/client";
import { ActionCell } from "../../components/ActionCell";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { useAsync } from "../../hooks/useAsync";
import type { AdminMetricKey } from "../../types/adminMetrics";
import { AdminDashboardScreen } from "./AdminDashboardScreen";

const ATTENTION_LABELS = {
  users_pending: "Новые регистрации",
  projects_review: "Проекты на проверке",
  events_pending: "События на согласовании",
  task_results: "Результаты заданий",
  activity_results: "Результаты активностей",
  rewards: "Заявки на возможности",
  portfolio: "Портфолио на проверке",
  reports: "Отчёты",
  questions: "Вопросы участников",
  departments: "Заявки по направлениям",
} as const;

type AttentionKey = keyof typeof ATTENTION_LABELS;
const ATTENTION_ORDER = Object.keys(ATTENTION_LABELS) as AttentionKey[];

interface AdminOverviewScreenProps {
  onOpenPeople: () => void;
  onOpenApplications: () => void;
  onOpenProjects: () => void;
  onOpenEvents: () => void;
  onOpenTasks: () => void;
  onOpenComms: () => void;
  onOpenOffers: () => void;
  onOpenCareer: () => void;
  onOpenVerification: () => void;
  onOpenMetric: (metric: AdminMetricKey, total: number) => void;
}

function KpiButton({ value, label, note, onClick }: { value: number; label: string; note: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} style={{ appearance: "none", border: 0, padding: 0, background: "transparent", textAlign: "left", minWidth: 0, cursor: "pointer" }}>
      <Card style={{ minHeight: 102, padding: "0.85rem" }}>
        <div style={{ fontSize: "1.75rem", fontWeight: 950, lineHeight: 1 }}>{value}</div>
        <strong style={{ display: "block", marginTop: "0.4rem" }}>{label}</strong>
        <span style={{ display: "block", marginTop: 3, color: "var(--era-text-muted)", fontSize: "0.72rem" }}>{note}</span>
      </Card>
    </button>
  );
}

export function AdminOverviewScreen({
  onOpenPeople,
  onOpenApplications,
  onOpenProjects,
  onOpenEvents,
  onOpenTasks,
  onOpenComms,
  onOpenOffers,
  onOpenCareer,
  onOpenVerification,
  onOpenMetric,
}: AdminOverviewScreenProps) {
  const dashboard = useAsync(() => fetchAdminDashboard(), []);
  const [showAnalytics, setShowAnalytics] = useState(false);

  if (dashboard.status === "loading") return <p style={{ color: "var(--era-text-muted)" }}>Загружаем пульт…</p>;
  if (dashboard.status === "error") return <EmptyState text="Не удалось загрузить пульт управления. Попробуйте ещё раз." />;

  const { metrics, attention_total } = dashboard.data;
  const roster = metrics.current_roster ?? metrics.users_total ?? 0;
  const activeBase = metrics.active_base ?? 0;
  const pending = metrics.users_pending ?? 0;
  const eventsLive = metrics.events_live ?? 0;
  const activeShare = roster > 0 ? Math.round((activeBase / roster) * 100) : 0;

  const attentionActions: Record<AttentionKey, () => void> = {
    users_pending: onOpenApplications,
    projects_review: onOpenProjects,
    events_pending: onOpenEvents,
    task_results: onOpenTasks,
    activity_results: onOpenEvents,
    rewards: onOpenOffers,
    portfolio: onOpenCareer,
    reports: () => setShowAnalytics(true),
    questions: onOpenComms,
    departments: onOpenPeople,
  };
  const attentionItems = ATTENTION_ORDER
    .map((key) => ({ key, label: ATTENTION_LABELS[key], value: metrics[key] ?? 0 }))
    .filter((item) => item.value > 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <Card gradient style={{ position: "relative", overflow: "hidden" }}>
        <p style={{ margin: "0 0 .3rem", color: "var(--era-text-secondary)", fontSize: "var(--era-text-xs)", fontWeight: 850, textTransform: "uppercase" }}>Пульт руководителя</p>
        <h1 style={{ margin: 0, fontSize: "clamp(1.7rem,7vw,2.25rem)", lineHeight: 1.05 }}>Что происходит в ЭРА</h1>
        <p style={{ margin: ".55rem 0 0", opacity: 0.78 }}>Главное, что требует решения — без перегруженной панели.</p>
        <div style={{ marginTop: ".8rem", display: "inline-flex", padding: ".38rem .65rem", borderRadius: 999, background: "var(--era-surface-2)", fontWeight: 850 }}>
          {attention_total > 0 ? `${attention_total} требуют внимания` : "Срочных решений нет ✓"}
        </div>
      </Card>

      <section aria-label="Сейчас">
        <h2 style={{ fontSize: ".82rem", color: "var(--era-text-muted)", margin: "0 0 .5rem", letterSpacing: ".04em" }}>СЕЙЧАС</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".5rem" }}>
          <KpiButton value={roster} label="Участники" note="Открыть состав →" onClick={() => onOpenMetric("current_roster", roster)} />
          <KpiButton value={activeBase} label="Активные" note={`${activeShare}% состава · 14 дней`} onClick={() => onOpenMetric("active_base", activeBase)} />
          <KpiButton value={pending} label="Новые заявки" note="Проверить регистрации →" onClick={onOpenApplications} />
          <KpiButton value={eventsLive} label="События" note="Текущие и ближайшие →" onClick={() => onOpenMetric("events_live", eventsLive)} />
        </div>
      </section>

      <section>
        <h2 style={{ fontSize: "var(--era-text-xl)", margin: "0 0 .5rem" }}>Нужно решить</h2>
        {attentionItems.length === 0 && (metrics.event_waitlist ?? 0) === 0 ? (
          <Card style={{ background: "var(--era-surface-2)", textAlign: "center", padding: ".9rem" }}>
            <strong>Очередь чистая ✓</strong>
            <p style={{ margin: ".25rem 0 0", color: "var(--era-text-muted)", fontSize: ".82rem" }}>Можно заниматься развитием, а не очередью.</p>
          </Card>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: ".45rem" }}>
            {(metrics.event_waitlist ?? 0) > 0 && <ActionCell title={`${metrics.event_waitlist} · лист ожидания`} description="Проверить места на событиях" leading="!" onClick={onOpenEvents} />}
            {attentionItems.slice(0, 5).map((item) => <ActionCell key={item.key} title={`${item.value} · ${item.label}`} description="Открыть и решить" leading="!" onClick={attentionActions[item.key]} />)}
            {attentionItems.length > 5 && <span style={{ color: "var(--era-text-muted)", fontSize: ".78rem" }}>Ещё {attentionItems.length - 5} пунктов доступны в соответствующих разделах.</span>}
          </div>
        )}
      </section>

      <section>
        <h2 style={{ fontSize: "var(--era-text-xl)", margin: "0 0 .5rem" }}>Быстро сделать</h2>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: ".5rem" }}>
          <ActionCell title="Мероприятие" description="Создать и вести" leading="＋" onClick={onOpenEvents} />
          <ActionCell title="Рассылка" description="Написать людям" leading="↗" onClick={onOpenComms} />
          <ActionCell title="Проект" description="Создать и проверить" leading="＋" onClick={onOpenProjects} />
          <ActionCell title="Участники" description="Состав и роли" leading="👥" onClick={onOpenPeople} />
        </div>
      </section>

      <section>
        <Card style={{ padding: ".9rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: ".75rem", alignItems: "center" }}>
            <div>
              <strong style={{ display: "block" }}>Регистрация и состав</strong>
              <span style={{ display: "block", marginTop: 3, color: "var(--era-text-muted)", fontSize: ".78rem" }}>Завершённые регистрации попадают в очередь заявок. Проверка состава — отдельный инструмент.</span>
            </div>
            <strong style={{ fontSize: "1.35rem" }}>{pending}</strong>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: ".5rem", marginTop: ".75rem" }}>
            <button type="button" className="era-btn-primary" onClick={onOpenApplications}>Заявки</button>
            <button type="button" onClick={onOpenVerification}>Состав</button>
          </div>
        </Card>
      </section>

      <section>
        <button type="button" onClick={() => setShowAnalytics((value) => !value)} style={{ width: "100%", border: 0, padding: 0, background: "transparent", textAlign: "left" }}>
          <Card style={{ padding: ".9rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: ".75rem" }}>
              <div>
                <strong style={{ display: "block" }}>Аналитика</strong>
                <span style={{ display: "block", marginTop: 3, color: "var(--era-text-muted)", fontSize: ".78rem" }}>Динамика, удержание и эффективность — только когда нужны.</span>
              </div>
              <span style={{ fontWeight: 900 }}>{showAnalytics ? "↑" : "→"}</span>
            </div>
          </Card>
        </button>
        {showAnalytics && <div style={{ marginTop: ".75rem" }}><AdminDashboardScreen /></div>}
      </section>
    </div>
  );
}
