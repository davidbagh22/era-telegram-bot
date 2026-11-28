import { useState } from "react";
import { fetchAdminDashboard, fetchRecentRegistrations } from "../../api/client";
import { ActionCell } from "../../components/ActionCell";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { useAsync } from "../../hooks/useAsync";
import type { AdminMetricKey } from "../../types/adminMetrics";
import { AdminDashboardScreen } from "./AdminDashboardScreen";
import { AdminDecisionQueueScreen } from "./AdminDecisionQueueScreen";

// Every item shown in "Решить сегодня" must open a screen where the admin can
// actually complete the task. Do not add informational counters here without
// a resolver flow — that creates dead-end cards on the command center.
const ATTENTION_LABELS = {
  users_pending: "Новые регистрации",
  projects_review: "Проекты на проверке",
  events_pending: "События на согласовании",
  attendance_proofs: "Фото-подтверждения участия",
  tasks_attention: "Задачи требуют внимания",
  questions: "Обращения ждут ответа",
  activity_results: "Результаты активностей",
  rewards: "Заявки на возможности",
  portfolio: "Портфолио на проверке",
} as const;

type AttentionKey = keyof typeof ATTENTION_LABELS;
const ATTENTION_ORDER = Object.keys(ATTENTION_LABELS) as AttentionKey[];

function openNativeQueue(payload: "admin_task_attention" | "admin_question_attention") {
  const url = `https://t.me/ERA_1bot?start=${payload}`;
  if (window.Telegram?.WebApp?.openTelegramLink) {
    window.Telegram.WebApp.openTelegramLink(url);
    window.Telegram.WebApp.close?.();
  }
  else window.open(url, "_blank", "noopener,noreferrer");
}

interface AdminOverviewScreenProps {
  onOpenPeople: () => void;
  onOpenApplications: () => void;
  onOpenProjects: () => void;
  onOpenProjectReview: () => void;
  onOpenEvents: () => void;
  onOpenEventCreate: () => void;
  onOpenEventModeration: () => void;
  onOpenEventWaitlist: () => void;
  onOpenActivityResults: () => void;
  onOpenAttendanceProofs: () => void;
  onOpenTasks: () => void;
  onOpenTaskCreate: () => void;
  onOpenTaskReview: () => void;
  onOpenBroadcast: () => void;
  onOpenComms: () => void;
  onOpenOffers: () => void;
  onOpenCareer: () => void;
  onOpenVerification: () => void;
  onOpenMetric: (metric: AdminMetricKey, total: number) => void;
  initialView?: "home" | "decisions";
}

function KpiButton({ value, label, note, onClick }: { value: number; label: string; note: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} style={{ appearance: "none", border: 0, padding: 0, background: "transparent", textAlign: "left", minWidth: 0, cursor: "pointer" }}>
      <Card style={{ minHeight: 96, padding: "0.8rem" }}>
        <div style={{ fontSize: "1.65rem", fontWeight: 950, lineHeight: 1 }}>{value}</div>
        <strong style={{ display: "block", marginTop: "0.35rem" }}>{label}</strong>
        <span style={{ display: "block", marginTop: 3, color: "var(--era-text-muted)", fontSize: "0.72rem" }}>{note}</span>
      </Card>
    </button>
  );
}

function registrationTime(value: string | null): string {
  if (!value) return "";
  const iso = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("ru-RU", { timeZone: "Asia/Yerevan", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(date);
}

function RecentRegistrations({ onOpen }: { onOpen: () => void }) {
  const recent = useAsync(() => fetchRecentRegistrations(5), []);
  return (
    <section aria-label="Последние записи">
      <h2 style={{ fontSize: "var(--era-text-xl)", margin: "0 0 .5rem" }}>Последние записи</h2>
      {recent.status === "loading" && <p style={{ color: "var(--era-text-muted)", margin: 0 }}>Загружаем записи…</p>}
      {recent.status === "error" && <p role="status" style={{ color: "var(--era-text-muted)", margin: 0 }}>Не удалось загрузить последние записи. Списки участников доступны в «Мероприятиях».</p>}
      {recent.status === "ready" && recent.data.length === 0 && <p style={{ color: "var(--era-text-muted)", margin: 0 }}>Пока никто не записался на мероприятия.</p>}
      {recent.status === "ready" && recent.data.length > 0 && (
        <Card style={{ padding: ".25rem .9rem" }}>
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {recent.data.map((item, index) => (
              <li key={item.registration_id} style={{ borderTop: index === 0 ? "none" : "1px solid var(--era-border)" }}>
                <button type="button" onClick={onOpen} style={{ appearance: "none", border: 0, background: "transparent", width: "100%", textAlign: "left", padding: ".65rem 0", display: "flex", justifyContent: "space-between", gap: ".75rem", color: "inherit", cursor: "pointer" }}>
                  <span style={{ minWidth: 0 }}>
                    <strong style={{ display: "block", overflowWrap: "anywhere" }}>{item.participant_name}</strong>
                    <span style={{ display: "block", color: "var(--era-text-muted)", fontSize: ".8rem", overflowWrap: "anywhere" }}>
                      {item.event_title}{item.status === "waitlist" ? " · лист ожидания" : ""}
                    </span>
                  </span>
                  <span style={{ flexShrink: 0, color: "var(--era-text-muted)", fontSize: ".78rem" }}>{registrationTime(item.registered_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </section>
  );
}

export function AdminOverviewScreen({
  onOpenPeople,
  onOpenApplications,
  onOpenProjects,
  onOpenProjectReview,
  onOpenEvents,
  onOpenEventCreate,
  onOpenEventModeration,
  onOpenEventWaitlist,
  onOpenActivityResults,
  onOpenAttendanceProofs,
  onOpenTasks,
  onOpenTaskCreate,
  onOpenTaskReview,
  onOpenBroadcast,
  onOpenComms,
  onOpenOffers,
  onOpenCareer,
  onOpenVerification,
  onOpenMetric,
  initialView = "home",
}: AdminOverviewScreenProps) {
  const [refreshKey, setRefreshKey] = useState(0);
  const dashboard = useAsync(() => fetchAdminDashboard(), [refreshKey]);
  const [showAnalytics, setShowAnalytics] = useState(false);
  const [showDecisions, setShowDecisions] = useState(initialView === "decisions");
  const [showMore, setShowMore] = useState(false);

  if (showAnalytics) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <button type="button" onClick={() => setShowAnalytics(false)} style={{ alignSelf: "flex-start" }}>← Пульт</button>
        <AdminDashboardScreen onAction={(action) => {
          const actions = { people: onOpenPeople, applications: onOpenApplications, events: onOpenEvents,
            projects: onOpenProjects, tasks: onOpenTasks, offers: onOpenOffers };
          setShowAnalytics(false); actions[action]();
        }} />
      </div>
    );
  }

  if (showDecisions) {
    return (
      <AdminDecisionQueueScreen
        onBack={() => setShowDecisions(false)}
        onOpenTaskReview={() => {
          setShowDecisions(false);
          onOpenTaskReview();
        }}
        onOpenNativeTaskQueue={() => openNativeQueue("admin_task_attention")}
        onChanged={() => setRefreshKey((value) => value + 1)}
      />
    );
  }

  const metrics = dashboard.status === "ready" ? dashboard.data.metrics : null;
  const attentionTotal = dashboard.status === "ready" ? dashboard.data.attention_total : 0;
  const pendingApplications = metrics ? (metrics.users_pending ?? 0) : null;
  const roster = metrics ? (metrics.current_roster ?? metrics.users_total ?? 0) : 0;
  const activeBase = metrics ? (metrics.active_base ?? 0) : 0;
  const pending = metrics ? (metrics.users_pending ?? 0) : 0;
  const eventsLive = metrics ? (metrics.events_live ?? 0) : 0;
  const activeShare = roster > 0 ? Math.round((activeBase / roster) * 100) : 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <Card gradient style={{ position: "relative", overflow: "hidden" }}>
        <p style={{ margin: "0 0 .3rem", color: "var(--era-text-secondary)", fontSize: "var(--era-text-xs)", fontWeight: 850, textTransform: "uppercase" }}>Пульт руководителя</p>
        <h1 style={{ margin: 0, fontSize: "clamp(1.7rem,7vw,2.25rem)", lineHeight: 1.05 }}>Что происходит в ЭРА</h1>
        {dashboard.status === "ready" && (
          <button
            type="button"
            onClick={() => setShowDecisions(true)}
            style={{ marginTop: ".8rem", display: "inline-flex", alignItems: "center", gap: ".35rem", padding: ".38rem .75rem", borderRadius: 999, border: 0, background: "var(--era-surface-2)", color: "inherit", fontWeight: 850, cursor: "pointer" }}
          >
            {attentionTotal > 0 ? `${attentionTotal} требуют внимания →` : "Срочных решений нет ✓"}
          </button>
        )}
      </Card>

      <section aria-label="Быстрые действия" data-testid="admin-quick-actions" style={{ display: "flex", flexDirection: "column", gap: ".5rem" }}>
        <h2 style={{ fontSize: ".82rem", color: "var(--era-text-muted)", margin: 0, letterSpacing: ".04em", textTransform: "uppercase" }}>Быстрые действия</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(92px, 1fr))", gap: ".5rem" }}>
          <button type="button" className="era-btn-primary" onClick={onOpenBroadcast} style={{ minHeight: "3.1rem", padding: ".6rem .5rem", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: ".15rem" }}>
            <strong>Рассылка</strong>
            <span style={{ fontSize: ".72rem", opacity: 0.9 }}>В ЛС или чат</span>
          </button>
          <button type="button" onClick={onOpenTaskCreate} style={{ minHeight: "3.1rem", padding: ".6rem .5rem", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: ".15rem" }}>
            <strong>Задание</strong>
            <span style={{ fontSize: ".72rem", color: "var(--era-text-muted)" }}>Дать задачу</span>
          </button>
          <button type="button" onClick={onOpenEventCreate} style={{ minHeight: "3.1rem", padding: ".6rem .5rem", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: ".15rem" }}>
            <strong>Мероприятие</strong>
            <span style={{ fontSize: ".72rem", color: "var(--era-text-muted)" }}>Создать</span>
          </button>
        </div>
      </section>

      <section aria-label="Сейчас" data-testid="admin-analytics-summary" style={{ display: "flex", flexDirection: "column", gap: ".55rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: ".5rem" }}>
          <h2 style={{ fontSize: ".82rem", color: "var(--era-text-muted)", margin: 0, letterSpacing: ".04em" }}>СЕЙЧАС</h2>
          <button type="button" onClick={() => setShowAnalytics(true)} style={{ padding: ".25rem .6rem", fontSize: ".78rem", minHeight: "auto" }}>
            Подробнее →
          </button>
        </div>
        {dashboard.status === "loading" && <p style={{ color: "var(--era-text-muted)", margin: 0 }}>Загружаем показатели…</p>}
        {dashboard.status === "error" && <EmptyState text="Не удалось загрузить пульт управления. Попробуйте ещё раз." />}
        {metrics && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".5rem" }}>
            <KpiButton value={roster} label="Участники" note="Открыть состав →" onClick={() => onOpenMetric("current_roster", roster)} />
            <KpiButton value={activeBase} label="Активные" note={`${activeShare}% состава · 14 дней`} onClick={() => onOpenMetric("active_base", activeBase)} />
            <KpiButton value={pending} label="Новые заявки" note="Проверить регистрации →" onClick={onOpenApplications} />
            <KpiButton value={eventsLive} label="События" note="Текущие и ближайшие →" onClick={() => onOpenMetric("events_live", eventsLive)} />
          </div>
        )}
        <button type="button" onClick={() => setShowAnalytics(true)} style={{ width: "100%", border: 0, padding: 0, background: "transparent", textAlign: "left", cursor: "pointer" }}>
          <Card style={{ padding: ".85rem .9rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: ".75rem" }}>
              <div style={{ minWidth: 0 }}>
                <strong style={{ display: "block" }}>Аналитика</strong>
                <span style={{ display: "block", marginTop: 3, color: "var(--era-text-muted)", fontSize: ".78rem", lineHeight: 1.45 }}>Динамика, удержание и эффективность — открыть отчёты.</span>
              </div>
              <span style={{ fontWeight: 900, flexShrink: 0 }}>→</span>
            </div>
          </Card>
        </button>
      </section>

      <section aria-label="Главное" data-testid="admin-primary-actions" style={{ display: "flex", flexDirection: "column", gap: ".5rem" }}>
        <ActionCell title="Мероприятия" description="Создать, списки участников, посещаемость" leading="◎" onClick={onOpenEvents} />
        <ActionCell title="Заявки" description="Новые регистрации и решения по ним" leading="✓" badge={pendingApplications} onClick={onOpenApplications} />
        <ActionCell title="Задачи" description="Создать задание и проверить результаты" leading="☰" onClick={onOpenTasks} />
      </section>

      <section aria-label="Очередь и списки" data-testid="admin-events-shortcuts" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: ".5rem" }}>
        <button type="button" onClick={() => setShowDecisions(true)}>
          Очередь решений{attentionTotal > 0 ? ` · ${attentionTotal}` : ""}
        </button>
        <button type="button" onClick={onOpenEventWaitlist}>Списки участников</button>
      </section>

      <RecentRegistrations onOpen={onOpenEventWaitlist} />

      <section aria-label="Ещё">
        <button
          type="button"
          aria-expanded={showMore}
          aria-controls="admin-more-tools"
          onClick={() => setShowMore((open) => !open)}
          style={{ width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center", gap: ".75rem", padding: ".85rem 1rem", textAlign: "left" }}
        >
          <strong style={{ fontSize: "var(--era-text-lg)" }}>Ещё{attentionTotal > 0 ? ` · ${attentionTotal}` : ""}</strong>
          <span aria-hidden="true">{showMore ? "▲" : "▼"}</span>
        </button>
        {showMore && (
          <div id="admin-more-tools" style={{ display: "flex", flexDirection: "column", gap: "1rem", marginTop: "1rem" }}>
            {dashboard.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загружаем пульт…</p>}
            {dashboard.status === "error" && <EmptyState text="Не удалось загрузить пульт управления. Попробуйте ещё раз." />}
            {metrics && <OverviewMoreTools
              metrics={metrics}
              attentionTotal={attentionTotal}
              onOpenPeople={onOpenPeople}
              onOpenApplications={onOpenApplications}
              onOpenProjects={onOpenProjects}
              onOpenProjectReview={onOpenProjectReview}
              onOpenEvents={onOpenEvents}
              onOpenEventModeration={onOpenEventModeration}
              onOpenEventWaitlist={onOpenEventWaitlist}
              onOpenActivityResults={onOpenActivityResults}
              onOpenAttendanceProofs={onOpenAttendanceProofs}
              onOpenBroadcast={onOpenBroadcast}
              onOpenComms={onOpenComms}
              onOpenOffers={onOpenOffers}
              onOpenCareer={onOpenCareer}
              onOpenVerification={onOpenVerification}
              onOpenDecisions={() => setShowDecisions(true)}
            />}
          </div>
        )}
      </section>
    </div>
  );
}

type MoreToolsProps = Omit<
  AdminOverviewScreenProps,
  "onOpenTasks" | "onOpenTaskCreate" | "onOpenTaskReview" | "onOpenEventCreate" | "onOpenMetric" | "initialView"
> & {
  metrics: Record<string, number>;
  attentionTotal: number;
  onOpenDecisions: () => void;
};

function OverviewMoreTools({
  metrics, onOpenPeople, onOpenApplications, onOpenProjects, onOpenProjectReview, onOpenEvents, onOpenEventModeration,
  onOpenEventWaitlist, onOpenActivityResults, onOpenAttendanceProofs, onOpenBroadcast, onOpenComms, onOpenOffers,
  onOpenCareer, onOpenVerification, onOpenDecisions,
}: MoreToolsProps) {
  const pending = metrics.users_pending ?? 0;

  const attentionActions: Record<AttentionKey, () => void> = {
    users_pending: onOpenApplications,
    projects_review: onOpenProjectReview,
    events_pending: onOpenEventModeration,
    attendance_proofs: onOpenAttendanceProofs,
    tasks_attention: onOpenDecisions,
    questions: () => openNativeQueue("admin_question_attention"),
    activity_results: onOpenActivityResults,
    rewards: onOpenOffers,
    portfolio: onOpenCareer,
  };
  const attentionItems = ATTENTION_ORDER
    .map((key) => ({ key, label: ATTENTION_LABELS[key], value: metrics[key] ?? 0 }))
    .filter((item) => item.value > 0);

  return (
    <>
      <section>
        <h2 style={{ fontSize: "var(--era-text-xl)", margin: "0 0 .5rem" }}>Решить сегодня</h2>
        {attentionItems.length === 0 && (metrics.event_waitlist ?? 0) === 0 ? (
          <Card style={{ background: "var(--era-surface-2)", textAlign: "center", padding: ".9rem" }}>
            <strong>Очередь чистая ✓</strong>
            <p style={{ margin: ".25rem 0 0", color: "var(--era-text-muted)", fontSize: ".82rem" }}>Можно заниматься развитием, а не очередью.</p>
          </Card>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: ".45rem" }}>
            {(metrics.event_waitlist ?? 0) > 0 && (
              <ActionCell
                title={`${metrics.event_waitlist} · лист ожидания`}
                description="Открыть участников и посещаемость"
                leading="!"
                onClick={onOpenEventWaitlist}
              />
            )}
            {attentionItems.map((item) => (
              <ActionCell
                key={item.key}
                title={`${item.value} · ${item.label}`}
                description={
                  item.key === "questions"
                    ? "Открыть рабочую очередь в боте"
                    : item.key === "tasks_attention"
                      ? "Открыть очередь решений и убрать неактуальное"
                      : "Открыть и решить"
                }
                leading="!"
                onClick={attentionActions[item.key]}
              />
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 style={{ fontSize: "var(--era-text-xl)", margin: "0 0 .5rem" }}>Быстро сделать</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: ".5rem" }}>
          <ActionCell title="Мероприятие" description="Создать и вести" leading="＋" onClick={onOpenEvents} />
          <ActionCell title="Редактировать мероприятие" description="Карточка, афиша и сообщения зарегистрированным" leading="✎" onClick={onOpenEventWaitlist} />
          <ActionCell title="Рассылка" description="Написать людям" leading="↗" onClick={onOpenBroadcast} />
          <ActionCell title="Центр связи" description="Чаты, приветствия, канал и автоконтент" leading="#" onClick={onOpenComms} />
          <ActionCell title="Проект" description="Создать и проверить" leading="＋" onClick={onOpenProjects} />
          <ActionCell title="Участники" description="Состав и роли" leading="👥" onClick={onOpenPeople} />
        </div>
      </section>

      <section>
        <Card style={{ padding: ".9rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: ".75rem", alignItems: "center" }}>
            <div style={{ minWidth: 0 }}>
              <strong style={{ display: "block" }}>Регистрация и состав</strong>
              <span style={{ display: "block", marginTop: 3, color: "var(--era-text-muted)", fontSize: ".78rem", lineHeight: 1.45 }}>Завершённые регистрации попадают в очередь заявок. Проверка состава — отдельный инструмент.</span>
            </div>
            <strong style={{ fontSize: "1.35rem", flexShrink: 0 }}>{pending}</strong>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: ".5rem", marginTop: ".75rem" }}>
            <button type="button" className="era-btn-primary" onClick={onOpenApplications}>Заявки</button>
            <button type="button" onClick={onOpenVerification}>Состав</button>
          </div>
        </Card>
      </section>
    </>
  );
}
