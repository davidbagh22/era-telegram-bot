import { fetchAdminDashboard, fetchEvents, fetchRecentActivity } from "../../api/client";
import { ActionCell } from "../../components/ActionCell";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { useAsync } from "../../hooks/useAsync";

const ATTENTION_LABELS: Record<string, string> = {
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
};

const ATTENTION_ORDER = Object.keys(ATTENTION_LABELS);

interface AdminOverviewScreenProps {
  onOpenPeople?: () => void;
  onOpenApplications?: () => void;
  onOpenProjects?: () => void;
  onOpenEvents?: () => void;
  onOpenTasks?: () => void;
  onOpenComms?: () => void;
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
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short" }).format(new Date(`${value}T00:00:00`));
}

function KpiButton({ value, label, note, onClick }: { value: number; label: string; note?: string; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      style={{
        appearance: "none",
        border: 0,
        padding: 0,
        background: "transparent",
        textAlign: "left",
        minWidth: 0,
        cursor: onClick ? "pointer" : "default",
      }}
    >
      <Card style={{ minHeight: 112, padding: "0.9rem", background: "linear-gradient(145deg, rgba(255,255,255,.06), rgba(255,255,255,.025))" }}>
        <div style={{ fontSize: "1.9rem", fontWeight: 950, lineHeight: 1 }}>{value}</div>
        <strong style={{ display: "block", marginTop: "0.45rem" }}>{label}</strong>
        <span style={{ display: "block", marginTop: 3, color: "var(--era-text-muted)", fontSize: "0.76rem" }}>{note ?? "Открыть список →"}</span>
      </Card>
    </button>
  );
}

export function AdminOverviewScreen({ onOpenPeople, onOpenApplications, onOpenProjects, onOpenEvents, onOpenTasks, onOpenComms }: AdminOverviewScreenProps) {
  const dashboard = useAsync(() => fetchAdminDashboard(), []);
  const activity = useAsync(() => fetchRecentActivity(), []);
  const upcoming = useAsync(() => fetchEvents("all"), []);

  if (dashboard.status === "loading") return <p style={{ color: "var(--era-text-muted)" }}>Загружаем пульт…</p>;
  if (dashboard.status === "error") return <EmptyState text="Не удалось загрузить пульт управления. Попробуйте ещё раз." />;

  const { metrics, attention_total } = dashboard.data;
  const attentionItems = ATTENTION_ORDER.map((key) => ({ key, label: ATTENTION_LABELS[key], value: metrics[key] ?? 0 })).filter((item) => item.value > 0);
  const attentionAction = (key: string): (() => void) | undefined => {
    if (key === "users_pending") return onOpenApplications;
    if (key === "projects_review") return onOpenProjects;
    if (key === "events_pending" || key === "activity_results") return onOpenEvents;
    if (key === "task_results") return onOpenTasks;
    if (["questions", "departments"].includes(key)) return onOpenComms;
    return undefined;
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.15rem" }}>
      <Card gradient style={{ position: "relative", overflow: "hidden", minHeight: 172 }}>
        <div aria-hidden="true" style={{ position: "absolute", inset: 0, background: "radial-gradient(70% 100% at 92% 0%, rgba(255,255,255,.2), transparent 62%)" }} />
        <div style={{ position: "relative" }}>
          <p style={{ margin: "0 0 .3rem", color: "rgba(255,255,255,.72)", fontSize: "var(--era-text-xs)", fontWeight: 850, textTransform: "uppercase" }}>Добрый день</p>
          <h1 style={{ margin: 0, fontSize: "clamp(1.75rem,7vw,2.35rem)", lineHeight: 1.04 }}>Вот что происходит в ЭРА сегодня</h1>
          <div style={{ marginTop: ".9rem", display: "inline-flex", padding: ".4rem .7rem", borderRadius: 999, background: "rgba(255,255,255,.14)", fontWeight: 850 }}>
            {attention_total > 0 ? `${attention_total} требуют реакции` : "Очередь чистая ✓"}
          </div>
        </div>
      </Card>

      <section>
        <h2 style={{ fontSize: ".86rem", color: "var(--era-text-muted)", margin: "0 0 .55rem" }}>ЖИВЫЕ ПОКАЗАТЕЛИ</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".55rem" }}>
          <KpiButton value={metrics.users_total ?? 0} label="Участники" onClick={onOpenPeople} />
          <KpiButton value={metrics.activists ?? 0} label="Активные" onClick={onOpenPeople} />
          <KpiButton value={metrics.projects_active ?? 0} label="Проекты" onClick={onOpenProjects} />
          <KpiButton value={metrics.events_live ?? 0} label="События" onClick={onOpenEvents} />
          <KpiButton value={metrics.event_registrations ?? 0} label="Регистрации" onClick={onOpenEvents} />
          <KpiButton value={metrics.task_results ?? 0} label="Задания на проверке" onClick={onOpenTasks} />
        </div>
      </section>

      <section>
        <h2 style={{ fontSize: "var(--era-text-xl)", margin: "0 0 .55rem" }}>Требует внимания</h2>
        {attention_total === 0 && (metrics.event_waitlist ?? 0) === 0 ? (
          <Card style={{ background: "rgba(255,255,255,.035)", textAlign: "center" }}>
            <div style={{ fontSize: "1.7rem" }}>✓</div>
            <strong>Очередь чистая</strong>
            <p style={{ margin: ".3rem 0 0", color: "var(--era-text-muted)" }}>Сейчас нет решений, которые нельзя откладывать.</p>
          </Card>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: ".5rem" }}>
            {(metrics.event_waitlist ?? 0) > 0 && <ActionCell title={`${metrics.event_waitlist} в листе ожидания`} description="Проверьте ближайшие события и свободные места" leading="◎" onClick={onOpenEvents} />}
            {attentionItems.map((item) => (
              <ActionCell key={item.key} title={`${item.value} · ${item.label}`} description={attentionAction(item.key) ? "Открыть и решить →" : "Посмотреть в соответствующем разделе"} leading="!" onClick={attentionAction(item.key)} />
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 style={{ fontSize: "var(--era-text-xl)", margin: "0 0 .55rem" }}>Быстрые действия</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: ".55rem" }}>
          {onOpenEvents && <ActionCell title="Создать мероприятие" description="Афиша → регистрация → напоминания → публикация" leading="＋" onClick={onOpenEvents} />}
          {onOpenProjects && <ActionCell title="Создать проект" description="Идея, команда, план и запуск" leading="＋" onClick={onOpenProjects} />}
          {onOpenTasks && <ActionCell title="Создать задание" description="Назначить результат, срок и баллы" leading="＋" onClick={onOpenTasks} />}
          {onOpenComms && <ActionCell title="Сделать рассылку" description="Личные сообщения, чаты и предпросмотр" leading="↗" onClick={onOpenComms} />}
        </div>
      </section>

      <section>
        <h2 style={{ fontSize: "var(--era-text-xl)", margin: "0 0 .55rem" }}>Ближайшие мероприятия</h2>
        {upcoming.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загружаем афишу…</p>}
        {upcoming.status === "error" && <EmptyState text="Не удалось загрузить ближайшие события." />}
        {upcoming.status === "ready" && upcoming.data.length === 0 && (
          <Card><strong>Пока нет ближайших мероприятий</strong><p style={{ margin: ".3rem 0 0", color: "var(--era-text-muted)" }}>Создайте первое событие — регистрация и участники будут собраны автоматически.</p>{onOpenEvents && <button type="button" className="era-btn-primary" onClick={onOpenEvents} style={{ marginTop: ".75rem", width: "100%" }}>Создать мероприятие</button>}</Card>
        )}
        {upcoming.status === "ready" && upcoming.data.slice(0, 3).map((event) => (
          <button key={event.id} type="button" onClick={onOpenEvents} style={{ width: "100%", border: 0, padding: 0, background: "transparent", textAlign: "left", marginBottom: ".5rem" }}>
            <Card style={{ padding: ".8rem .9rem" }}>
              <div style={{ display: "flex", gap: ".8rem", alignItems: "center" }}>
                <div style={{ minWidth: 52, textAlign: "center" }}><strong style={{ display: "block", fontSize: "1.25rem" }}>{formatEventDate(event.event_date).split(" ")[0]}</strong><span style={{ color: "var(--era-text-muted)", fontSize: ".74rem" }}>{formatEventDate(event.event_date).split(" ").slice(1).join(" ")}</span></div>
                <div style={{ minWidth: 0, flex: 1 }}><strong style={{ display: "block", overflowWrap: "anywhere" }}>{event.title}</strong><span style={{ color: "var(--era-text-muted)", fontSize: ".8rem" }}>{event.participant_limit ? `${event.registered_count} / ${event.participant_limit} участников` : `${event.registered_count} участников`} · {event.event_time}</span></div>
                <span>→</span>
              </div>
            </Card>
          </button>
        ))}
      </section>

      <section>
        <h2 style={{ fontSize: ".86rem", color: "var(--era-text-muted)", margin: "0 0 .5rem" }}>ПОСЛЕДНЯЯ АКТИВНОСТЬ</h2>
        {activity.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
        {activity.status === "error" && <EmptyState text="Не удалось загрузить активность." />}
        {activity.status === "ready" && activity.data.length === 0 && <EmptyState text="Пока нет новых действий. Они появятся здесь после первых изменений." />}
        {activity.status === "ready" && activity.data.slice(0, 8).map((entry) => (
          <div key={entry.id} style={{ display: "flex", justifyContent: "space-between", gap: ".6rem", padding: ".55rem 0", borderBottom: "1px solid var(--era-border)", fontSize: ".8rem" }}>
            <span style={{ overflowWrap: "anywhere" }}>{entry.actor_name ? <strong>{entry.actor_name} </strong> : null}{entry.summary}</span>
            <span style={{ color: "var(--era-text-muted)", whiteSpace: "nowrap" }}>{timeAgo(entry.created_at)}</span>
          </div>
        ))}
      </section>
    </div>
  );
}
