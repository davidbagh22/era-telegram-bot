import type { ReactNode } from "react";
import { Avatar } from "../components/Avatar";
import { Card } from "../components/Card";
import { EraScore } from "../components/EraScore";
import { EmptyState } from "../components/EmptyState";
import { EventCard } from "../components/EventCard";
import { IconButton, SecondaryButton } from "../components/Buttons";
import { OpportunityCard } from "../components/OpportunityCard";
import { Skeleton, SkeletonCard } from "../components/Skeleton";
import { BellIcon, ChevronRightIcon, EventIcon, OpportunitiesIcon, ProjectsIcon, TaskIcon } from "../components/icons";
import { fetchEvents, fetchOpportunities, fetchTasks } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import { useHome } from "../hooks/useHome";
import type { MiniAppUserSummary } from "../types/auth";

interface HomeScreenProps { user: MiniAppUserSummary; }

function localIsoDate(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function route(path: string): void {
  const hash = `#/${path}`;
  if (window.location.hash === hash) window.scrollTo({ top: 0, behavior: "smooth" });
  else window.location.hash = hash;
}

export function HomeScreen({ user }: HomeScreenProps) {
  const home = useHome();
  const events = useAsync(() => fetchEvents("for_me"), []);
  const tasks = useAsync(() => fetchTasks("available"), []);
  const opportunities = useAsync(() => fetchOpportunities("for_me"), []);

  if (home.status === "loading") {
    return <div className="era-page era-page-shell"><div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}><Skeleton width={48} height={48} radius="50%" /><div style={{ flex: 1, display: "grid", gap: 6 }}><Skeleton height="1.1rem" width="55%" /><Skeleton height="0.75rem" width="35%" /></div><Skeleton width={44} height={44} radius="50%" /></div><Skeleton height="9.5rem" radius="var(--era-radius-card)" /><SkeletonCard /><SkeletonCard /></div>;
  }
  if (home.status === "error") return <div className="era-page era-page-shell"><EmptyState title="Главная пока не загрузилась" description="Проверьте соединение и откройте ЭРА ещё раз. Ваши данные не изменились." /></div>;

  const { data } = home;
  const levelPercent = data.growth.level_count <= 1 ? 100 : (data.growth.level_index / (data.growth.level_count - 1)) * 100;
  const today = localIsoDate();
  const eventItems = events.status === "ready" ? events.data : [];
  const taskItems = tasks.status === "ready" ? tasks.data : [];
  const opportunityItems = opportunities.status === "ready" ? opportunities.data : [];
  const todayEvents = eventItems.filter((item) => item.event_date === today);
  const nearestEvent = [...eventItems].filter((item) => item.event_date >= today).sort((a, b) => `${a.event_date}T${a.event_time}`.localeCompare(`${b.event_date}T${b.event_time}`))[0] ?? null;
  const openTasks = taskItems.filter((item) => item.status !== "completed");

  return (
    <div className="era-page era-page-shell">
      <header style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
        <button type="button" aria-label="Открыть профиль" onClick={() => route("profile")} style={{ all: "unset", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.75rem", minWidth: 0, flex: 1 }}>
          <Avatar firstName={user.first_name} lastName={user.last_name} />
          <div style={{ minWidth: 0 }}><p className="era-kicker">ЭРА сегодня</p><strong style={{ display: "block", marginTop: 2, fontSize: "var(--era-text-lg)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{user.first_name}{user.last_name ? ` ${user.last_name}` : ""}</strong><span style={{ color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>{data.growth.label} · путь в ЭРА</span></div>
        </button>
        <IconButton label="Уведомления" onClick={() => route("notifications")}><BellIcon width={21} height={21} /></IconButton>
      </header>

      <EraScore score={data.points_balance} progressPercent={levelPercent} levelLabel={data.growth.label} onClick={() => route("progress")} />

      <section className="era-section">
        <h2 className="era-section-title">Сегодня</h2>
        <div className="era-grid-2">
          <QuickMetric icon={<EventIcon width={19} height={19} />} value={todayEvents.length} label={todayEvents.length ? "события сегодня" : "событий сегодня нет"} action={() => route("events")} />
          <QuickMetric icon={<TaskIcon width={19} height={19} />} value={openTasks.length} label="открытых задач" action={() => route("tasks")} />
          <QuickMetric icon={<OpportunitiesIcon width={19} height={19} />} value={opportunityItems.length} label="подходит вам" action={() => route("opportunities")} />
          <QuickMetric icon={<ProjectsIcon width={19} height={19} />} value={data.activity.projects} label="ваших проектов" action={() => route("projects")} />
        </div>
      </section>

      <section className="era-section">
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "center" }}><h2 className="era-section-title">Ближайшее событие</h2><SecondaryButton onClick={() => route("events")} style={{ minHeight: 40, padding: "0.45rem 0.75rem" }}>Все</SecondaryButton></div>
        {events.status === "loading" && <SkeletonCard />}
        {events.status === "error" && <EmptyState title="Афиша не загрузилась" description="Главная доступна, но список событий сейчас не получен." actionLabel="Открыть события" onAction={() => route("events")} />}
        {events.status === "ready" && nearestEvent && <EventCard event={nearestEvent} featured onClick={() => route(`events/${nearestEvent.id}`)} />}
        {events.status === "ready" && !nearestEvent && <EmptyState title="Ближайших событий пока нет" description="Как только появится новое событие ЭРА, оно будет здесь." actionLabel="Открыть афишу" onAction={() => route("events")} />}
      </section>

      <section className="era-section">
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "center" }}><div><h2 className="era-section-title">Для тебя</h2><p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>Только предложения, которые система связала с вашим профилем.</p></div><SecondaryButton onClick={() => route("opportunities")} style={{ minHeight: 40, padding: "0.45rem 0.75rem" }}>Все</SecondaryButton></div>
        {opportunities.status === "loading" && <SkeletonCard />}
        {opportunities.status === "error" && <EmptyState title="Подборка пока недоступна" description="Возможности не потеряны — откройте раздел чуть позже." />}
        {opportunities.status === "ready" && opportunityItems.length > 0 && <div style={{ display: "grid", gap: "0.75rem" }}>{opportunityItems.slice(0, 3).map((item) => <OpportunityCard key={item.id} opportunity={item} onClick={() => route(`opportunities/${item.id}`)} />)}</div>}
        {opportunities.status === "ready" && opportunityItems.length === 0 && <EmptyState title="Новых совпадений пока нет" description="Подборка меняется вместе с вашей активностью и интересами." actionLabel="Посмотреть все возможности" onAction={() => route("opportunities")} />}
      </section>

      {data.next_step && <Card interactive onClick={() => {
        const kind = data.next_step?.kind;
        if (kind === "event") route("events");
        else if (kind === "project") route("projects");
        else if (kind === "task") route("tasks");
        else if (kind === "opportunity") route("opportunities");
        else route("progress");
      }} ariaLabel="Открыть следующий шаг" style={{ borderColor: "rgba(227,38,54,.12)" }}><p className="era-kicker">Следующий шаг</p><div style={{ display: "flex", gap: "0.75rem", alignItems: "center", marginTop: "0.35rem" }}><div style={{ flex: 1 }}><strong style={{ fontSize: "var(--era-text-lg)" }}>{data.next_step.title}</strong><p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>{data.next_step.description}</p></div><ChevronRightIcon width={20} height={20} style={{ color: "var(--era-red)", flexShrink: 0 }} /></div></Card>}
    </div>
  );
}

function QuickMetric({ icon, value, label, action }: { icon: ReactNode; value: number; label: string; action: () => void }) {
  return <Card interactive onClick={action} ariaLabel={`${value} ${label}. Открыть`} style={{ minHeight: 112, boxShadow: "none" }}><span style={{ width: 36, height: 36, borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--era-red)", background: "var(--era-tint-red)" }}>{icon}</span><strong className="era-number" style={{ display: "block", marginTop: "0.75rem", fontSize: "1.8rem", lineHeight: 1 }}>{value}</strong><span style={{ display: "block", marginTop: 5, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>{label}</span></Card>;
}
