import { fetchAdminDashboard, fetchEvents, fetchRecentActivity } from "../../api/client";
import { fetchSystemSnapshot } from "../../api/systemClient";
import { ActionCell } from "../../components/ActionCell";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { useAsync } from "../../hooks/useAsync";
import type { AdminMetricKey } from "../../types/adminMetrics";
import { AdminDashboardScreen } from "./AdminDashboardScreen";
import { SystemPanel } from "./tools/SystemPanel";

const ATTENTION_LABELS = {
  users_pending: "Новые заявки ждут решения",
  projects_review: "Проекты ждут проверки",
  events_pending: "События ждут согласования",
  task_results: "Задания ждут проверки",
  activity_results: "Результаты активностей ждут проверки",
  rewards: "Заявки на возможности ждут решения",
  portfolio: "Портфолио ждёт проверки",
  reports: "Отчёты требуют внимания",
  questions: "Есть новые вопросы участников",
  departments: "Есть заявки по направлениям",
} as const;

type AttentionKey = keyof typeof ATTENTION_LABELS;
const ATTENTION_ORDER = Object.keys(ATTENTION_LABELS) as AttentionKey[];

interface AdminOverviewScreenProps {
  onOpenPeople: () => void;
  onOpenApplications: () => void;
  onOpenVerification: () => void;
  onOpenDevelopment: () => void;
  onOpenCareer: () => void;
  onOpenOffices: () => void;
  onOpenDataRights: () => void;
  onOpenProjects: () => void;
  onOpenEvents: () => void;
  onOpenTasks: () => void;
  onOpenOffers: () => void;
  onOpenSurveys: () => void;
  onOpenComms: () => void;
  onOpenMetric: (metric: AdminMetricKey, total: number) => void;
}

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "только что";
  if (minutes < 60) return `${minutes} мин назад`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} ч назад`;
  return `${Math.round(hours / 24)} дн назад`;
}

function formatEventDate(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short" }).format(
    new Date(`${value}T00:00:00`),
  );
}

function KpiButton({ value, label, note, onClick }: { value: number; label: string; note?: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} style={{ appearance: "none", border: 0, padding: 0, background: "transparent", textAlign: "left", minWidth: 0, cursor: "pointer" }}>
      <Card style={{ minHeight: 112, padding: "0.9rem" }}>
        <div style={{ fontSize: "1.9rem", fontWeight: 950, lineHeight: 1 }}>{value}</div>
        <strong style={{ display: "block", marginTop: "0.45rem" }}>{label}</strong>
        <span style={{ display: "block", marginTop: 3, color: "var(--era-text-muted)", fontSize: "0.76rem" }}>{note ?? "Открыть точный список →"}</span>
      </Card>
    </button>
  );
}

function openInlineSystem() {
  const details = document.getElementById("admin-system-detail") as HTMLDetailsElement | null;
  if (!details) return;
  details.open = true;
  details.scrollIntoView({ behavior: "smooth", block: "start" });
}

function scrollToAnalytics() {
  document.getElementById("admin-analytics")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export function AdminOverviewScreen({
  onOpenPeople,
  onOpenApplications,
  onOpenVerification,
  onOpenDevelopment,
  onOpenCareer,
  onOpenOffices,
  onOpenDataRights,
  onOpenProjects,
  onOpenEvents,
  onOpenTasks,
  onOpenOffers,
  onOpenSurveys,
  onOpenComms,
  onOpenMetric,
}: AdminOverviewScreenProps) {
  const dashboard = useAsync(() => fetchAdminDashboard(), []);
  const activity = useAsync(() => fetchRecentActivity(), []);
  const upcoming = useAsync(() => fetchEvents("all"), []);
  const system = useAsync(() => fetchSystemSnapshot(), []);

  if (dashboard.status === "loading") return <p style={{ color: "var(--era-text-muted)" }}>Собираем пульт ЭРА…</p>;
  if (dashboard.status === "error") return <EmptyState text="Не удалось загрузить пульт управления. Попробуйте ещё раз." />;

  const { metrics, attention_total } = dashboard.data;
  const attentionItems = ATTENTION_ORDER.map((key) => ({ key, label: ATTENTION_LABELS[key], value: metrics[key] ?? 0 })).filter((item) => item.value > 0);
  const attentionActions: Record<AttentionKey, () => void> = {
    users_pending: onOpenApplications,
    projects_review: onOpenProjects,
    events_pending: onOpenEvents,
    task_results: onOpenTasks,
    activity_results: onOpenEvents,
    rewards: onOpenOffers,
    portfolio: onOpenCareer,
    reports: scrollToAnalytics,
    questions: onOpenComms,
    departments: onOpenPeople,
  };

  const latestHealth = system.status === "ready" ? system.data.latest : null;
  const healthIssues = latestHealth?.checks.filter((check) => check.status !== "ok") ?? [];
  const roster = metrics.current_roster ?? metrics.users_total ?? 0;
  const activeBase = metrics.active_base ?? 0;
  const projectsActive = metrics.projects_active ?? 0;
  const eventsLive = metrics.events_live ?? 0;
  const registrations = metrics.event_registrations ?? 0;
  const taskResults = metrics.task_results ?? 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.15rem" }}>
      <Card gradient style={{ position: "relative", overflow: "hidden", minHeight: 172 }}>
        <div aria-hidden="true" style={{ position: "absolute", inset: 0, background: "radial-gradient(70% 100% at 92% 0%, rgba(255,255,255,.2), transparent 62%)" }} />
        <div style={{ position: "relative" }}>
          <p style={{ margin: "0 0 .3rem", color: "var(--era-text-secondary)", fontSize: "var(--era-text-xs)", fontWeight: 850, textTransform: "uppercase" }}>Admin Command Center</p>
          <h1 style={{ margin: 0, fontSize: "clamp(1.75rem,7vw,2.35rem)", lineHeight: 1.04 }}>ЭРА сейчас — вся картина сразу</h1>
          <p style={{ margin: ".55rem 0 0", color: "var(--era-text-secondary)", maxWidth: 520 }}>Показатели, риски, очередь решений, состояние системы и управление — без отдельного раздела «Аналитика».</p>
          <div style={{ marginTop: ".9rem", display: "inline-flex", padding: ".4rem .7rem", borderRadius: 999, background: "var(--era-tint-violet)", color: "var(--era-violet)", fontWeight: 850 }}>
            {attention_total > 0 ? `${attention_total} требуют реакции` : "Очередь чистая ✓"}
          </div>
        </div>
      </Card>

      <button type="button" onClick={openInlineSystem} style={{ width: "100%", border: 0, padding: 0, background: "transparent", textAlign: "left" }}>
        <Card style={{ padding: ".8rem 1rem" }}>
          {system.status === "loading" && <span style={{ color: "var(--era-text-muted)" }}>Проверяем API · Bot · Telegram · DB · Backup…</span>}
          {system.status === "error" && <strong style={{ color: "var(--era-error)" }}>Health API недоступен · показать диагностику →</strong>}
          {system.status === "ready" && !latestHealth && <strong>Health: нет данных · показать диагностику →</strong>}
          {latestHealth && healthIssues.length === 0 && <div style={{ display: "flex", justifyContent: "space-between", gap: ".75rem", alignItems: "center" }}><strong>Система в порядке</strong><span style={{ color: "var(--era-success)", fontWeight: 850 }}>{latestHealth.score}/100 ✓</span></div>}
          {latestHealth && healthIssues.length > 0 && <div><strong style={{ color: "var(--era-error)" }}>{healthIssues.length} системных проблем · {latestHealth.score}/100</strong><span style={{ display: "block", marginTop: ".25rem", color: "var(--era-text-muted)", fontSize: ".76rem" }}>{healthIssues.slice(0, 3).map((item) => item.title).join(" · ")}{healthIssues.length > 3 ? " · …" : ""} →</span></div>}
        </Card>
      </button>

      <section>
        <div style={{ display: "flex", justifyContent: "space-between", gap: ".6rem", alignItems: "end", marginBottom: ".55rem" }}>
          <div><p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Live</p><h2 style={{ margin: ".1rem 0 0", fontSize: "var(--era-text-xl)" }}>Главные показатели</h2></div>
          <button type="button" onClick={scrollToAnalytics} style={{ minHeight: 36, padding: ".35rem .6rem", fontSize: ".74rem" }}>Вся аналитика ↓</button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".55rem" }}>
          <KpiButton value={roster} label="Участники" note="Подтверждённый состав" onClick={() => onOpenMetric("current_roster", roster)} />
          <KpiButton value={activeBase} label="Активная база" note="Meaningful Activity · 14 дней" onClick={() => onOpenMetric("active_base", activeBase)} />
          <KpiButton value={projectsActive} label="Проекты" onClick={() => onOpenMetric("projects_active", projectsActive)} />
          <KpiButton value={eventsLive} label="События" onClick={() => onOpenMetric("events_live", eventsLive)} />
          <KpiButton value={registrations} label="Регистрации" onClick={() => onOpenMetric("event_registrations", registrations)} />
          <KpiButton value={taskResults} label="На проверке" note="Результаты заданий" onClick={() => onOpenMetric("task_results", taskResults)} />
        </div>
      </section>

      <section>
        <h2 style={{ fontSize: "var(--era-text-xl)", margin: "0 0 .55rem" }}>Требует внимания</h2>
        {attention_total === 0 && (metrics.event_waitlist ?? 0) === 0 ? (
          <Card style={{ background: "var(--era-surface-2)", textAlign: "center" }}><div style={{ fontSize: "1.7rem" }}>✓</div><strong>Очередь чистая</strong><p style={{ margin: ".3rem 0 0", color: "var(--era-text-muted)" }}>Сейчас нет решений, которые нельзя откладывать.</p></Card>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: ".5rem" }}>
            {(metrics.event_waitlist ?? 0) > 0 && <ActionCell title={`${metrics.event_waitlist} в листе ожидания`} description="Проверьте ближайшие события и свободные места" leading="◎" onClick={onOpenEvents} />}
            {attentionItems.map((item) => <ActionCell key={item.key} title={`${item.value} · ${item.label}`} description="Открыть и решить →" leading="!" onClick={attentionActions[item.key]} />)}
          </div>
        )}
      </section>

      <section>
        <div style={{ marginBottom: ".55rem" }}><p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Управление</p><h2 style={{ margin: ".1rem 0 0", fontSize: "var(--era-text-xl)" }}>Все рабочие зоны</h2></div>
        <div style={{ display: "flex", flexDirection: "column", gap: ".55rem" }}>
          <ActionCell title="Новые заявки" description="Регистрации: одобрить, запросить данные или отклонить" leading="◎" onClick={onOpenApplications} />
          <ActionCell title="Участники" description="Состав, роли и карточки участников" leading="👥" onClick={onOpenPeople} />
          <ActionCell title="Проверка актуального состава" description="Community Verification, напоминания и ручные решения" leading="✓" onClick={onOpenVerification} />
          <ActionCell title="Мероприятия" description="Создание, согласование, регистрации, посещаемость и активности" leading="◉" onClick={onOpenEvents} />
          <ActionCell title="Проекты" description="Создание, модерация, команды и результаты" leading="◆" onClick={onOpenProjects} />
          <ActionCell title="Задания" description="Создание задач и проверка результатов" leading="✓" onClick={onOpenTasks} />
          <ActionCell title="Возможности" description="Партнёрские предложения, заявки и награды" leading="★" onClick={onOpenOffers} />
          <ActionCell title="Центр связи" description="Чаты, FAQ, приветствия, рассылки и автоконтент" leading="↗" onClick={onOpenComms} />
          <ActionCell title="Опросы" description="Обратная связь и активные опросы" leading="?" onClick={onOpenSurveys} />
          <ActionCell title="Состояние и развитие" description="Добровольные Check-in, охват и потребности сообщества" leading="◌" onClick={onOpenDevelopment} />
          <ActionCell title="Портфолио и рекомендации" description="Проверка достижений и официальные рекомендации" leading="▣" onClick={onOpenCareer} />
          <ActionCell title="Должности и роли" description="Организационная структура и назначения" leading="◇" onClick={onOpenOffices} />
          <ActionCell title="Данные и права" description="Экспорт и удаление персональных данных" leading="⌁" onClick={onOpenDataRights} />
        </div>
      </section>

      <section>
        <h2 style={{ fontSize: "var(--era-text-xl)", margin: "0 0 .55rem" }}>Ближайшие мероприятия</h2>
        {upcoming.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загружаем афишу…</p>}
        {upcoming.status === "error" && <EmptyState text="Не удалось загрузить ближайшие события." />}
        {upcoming.status === "ready" && upcoming.data.length === 0 && <EmptyState text="Пока нет ближайших мероприятий." />}
        {upcoming.status === "ready" && upcoming.data.slice(0, 3).map((event) => (
          <button key={event.id} type="button" onClick={onOpenEvents} style={{ width: "100%", border: 0, padding: 0, background: "transparent", textAlign: "left", marginBottom: ".5rem" }}>
            <Card style={{ padding: ".8rem .9rem" }}><div style={{ display: "flex", gap: ".8rem", alignItems: "center" }}><div style={{ minWidth: 52, textAlign: "center" }}><strong style={{ display: "block", fontSize: "1.25rem" }}>{formatEventDate(event.event_date).split(" ")[0]}</strong><span style={{ color: "var(--era-text-muted)", fontSize: ".74rem" }}>{formatEventDate(event.event_date).split(" ").slice(1).join(" ")}</span></div><div style={{ minWidth: 0, flex: 1 }}><strong style={{ display: "block", overflowWrap: "anywhere" }}>{event.title}</strong><span style={{ color: "var(--era-text-muted)", fontSize: ".8rem" }}>{event.participant_limit ? `${event.registered_count} / ${event.participant_limit} участников` : `${event.registered_count} участников`} · {event.event_time}</span></div><span>→</span></div></Card>
          </button>
        ))}
      </section>

      <section id="admin-analytics" style={{ scrollMarginTop: 16 }}>
        <div style={{ marginBottom: ".7rem" }}><p style={{ margin: 0, color: "var(--era-violet)", fontSize: "var(--era-text-xs)", fontWeight: 850, textTransform: "uppercase" }}>Аналитика встроена в пульт</p><h2 style={{ margin: ".15rem 0 0", fontSize: "var(--era-text-2xl)" }}>Эффективность, Пульс и здоровье ЭРА</h2><p style={{ margin: ".35rem 0 0", color: "var(--era-text-muted)" }}>Никакого отдельного окна: управленческие показатели находятся прямо здесь.</p></div>
        <AdminDashboardScreen />
      </section>

      <details id="admin-system-detail" style={{ scrollMarginTop: 16 }}>
        <summary style={{ cursor: "pointer", fontWeight: 850, padding: ".9rem 0" }}>Техническая диагностика · API / Bot / Telegram / DB / Backup</summary>
        <div style={{ paddingTop: ".6rem" }}><SystemPanel /></div>
      </details>

      <section>
        <h2 style={{ fontSize: ".86rem", color: "var(--era-text-muted)", margin: "0 0 .5rem" }}>ПОСЛЕДНЯЯ АКТИВНОСТЬ</h2>
        {activity.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
        {activity.status === "error" && <EmptyState text="Не удалось загрузить активность." />}
        {activity.status === "ready" && activity.data.length === 0 && <EmptyState text="Пока нет новых действий." />}
        {activity.status === "ready" && activity.data.slice(0, 8).map((entry) => <div key={entry.id} style={{ display: "flex", justifyContent: "space-between", gap: ".6rem", padding: ".55rem 0", borderBottom: "1px solid var(--era-border)", fontSize: ".8rem" }}><span style={{ overflowWrap: "anywhere" }}>{entry.actor_name ? <strong>{entry.actor_name} </strong> : null}{entry.summary}</span><span style={{ color: "var(--era-text-muted)", whiteSpace: "nowrap" }}>{timeAgo(entry.created_at)}</span></div>)}
      </section>
    </div>
  );
}
