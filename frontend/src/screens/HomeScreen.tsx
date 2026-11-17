import { useEffect, useState, type ReactNode } from "react";
import { fetchDailyQuote, fetchEvents } from "../api/client";
import { Avatar } from "../components/Avatar";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { MonoLabel } from "../components/MonoLabel";
import { PosterCard } from "../components/PosterCard";
import { Skeleton, SkeletonCard } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import { EventIcon, ProjectsIcon, TaskIcon } from "../components/icons";
import { useHome } from "../hooks/useHome";
import type { EventItem } from "../types/activity";
import type { MiniAppUserSummary } from "../types/auth";
import { AnniversaryRegistration } from "./activity/AnniversaryRegistration";
import { EventPoster } from "./activity/EventsTab";

interface HomeScreenProps {
  user: MiniAppUserSummary;
  onOpenProfile?: () => void;
  onOpenProgress?: () => void;
  onOpenDevelopment?: () => void;
  onOpenAssessments?: () => void;
  onOpenEvents?: () => void;
  onOpenEvent?: (id: number) => void;
  onOpenProject?: (id: number) => void;
  onOpenTask?: (id: number) => void;
  onOpenTasks?: () => void;
  onOpenCommunity?: () => void;
  onOpenOpportunity?: (id: number) => void;
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" }).replace(".", "");
}

function greeting() {
  const hour = new Date().getHours();
  if (hour < 5) return "Доброй ночи";
  if (hour < 12) return "Доброе утро";
  if (hour < 18) return "Добрый день";
  return "Добрый вечер";
}

function IconBubble({ children, tone }: { children: ReactNode; tone: "violet" | "orange" | "magenta" }) {
  const styles = {
    violet: { background: "var(--era-tint-violet)", color: "var(--era-violet)" },
    orange: { background: "var(--era-tint-gold)", color: "var(--era-gold-ink)" },
    magenta: { background: "rgba(215,25,120,0.10)", color: "var(--era-magenta)" },
  }[tone];
  return (
    <span style={{ flexShrink: 0, width: 40, height: 40, borderRadius: "50%", display: "grid", placeItems: "center", ...styles }}>
      {children}
    </span>
  );
}

export function HomeScreen({
  user,
  onOpenProfile,
  onOpenDevelopment,
  onOpenAssessments,
  onOpenEvents,
  onOpenEvent,
  onOpenProject,
  onOpenTask,
  onOpenTasks,
  onOpenCommunity,
  onOpenOpportunity,
}: HomeScreenProps) {
  const home = useHome();
  const [dailyQuote, setDailyQuote] = useState("");
  const [eventBoard, setEventBoard] = useState<EventItem[] | "loading" | "error">("loading");

  useEffect(() => {
    let active = true;
    void fetchEvents("all").then((events) => {
      if (active) setEventBoard(events.filter((event) => ["approved", "published", "registration_open", "registration_closed"].includes(event.status)));
    }).catch(() => { if (active) setEventBoard("error"); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    void fetchDailyQuote().then((item) => {
      if (active) setDailyQuote(item.text);
    }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  if (home.status === "loading") {
    return (
      <div className="era-page" style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <Skeleton width={44} height={44} radius="50%" />
          <div style={{ flex: 1 }}><Skeleton height="1.1rem" width="58%" /></div>
        </div>
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (home.status === "error") {
    return <StatusBanner title="Не получилось загрузить главную" description="Проверь соединение и открой экран ещё раз." />;
  }

  const { data } = home;
  const featuredEvent = data.featured_event;
  const upcomingEvents = Array.isArray(eventBoard)
    ? eventBoard.filter((event) => event.id !== featuredEvent?.id)
    : [];
  const nearestEvent = data.nearest_event?.id === featuredEvent?.id
    || upcomingEvents.slice(0, 3).some((event) => event.id === data.nearest_event?.id)
    ? null : data.nearest_event;

  const nextStepClick = (() => {
    if (!data.next_step) return undefined;
    const { kind, entity_id } = data.next_step;
    if (kind === "task" && entity_id != null && onOpenTask) return () => onOpenTask(entity_id);
    if (kind === "event" && entity_id != null && onOpenEvent) return () => onOpenEvent(entity_id);
    if (kind === "project" && entity_id != null && onOpenProject) return () => onOpenProject(entity_id);
    if (kind === "opportunity" && entity_id != null && onOpenOpportunity) return () => onOpenOpportunity(entity_id);
    if (kind === "growth" && user.features.vector && onOpenDevelopment) return onOpenDevelopment;
    return undefined;
  })();

  const confirmedResult = data.activity.completed_tasks > 0
    ? `Выполнено заданий: ${data.activity.completed_tasks}`
    : (data.activity.attended_events ?? 0) > 0
      ? `Подтверждено посещений: ${data.activity.attended_events}`
      : (data.activity.completed_projects ?? 0) > 0
        ? `Завершено проектов: ${data.activity.completed_projects}`
        : (data.activity.verified_portfolio_items ?? 0) > 0
          ? `Подтверждено записей: ${data.activity.verified_portfolio_items}`
          : null;
  const nextStepIsTask = data.next_step?.kind === "task"
    && data.next_step.entity_id === data.active_task?.id;

  return (
    <div className="era-page era-stagger" style={{ padding: "1.15rem 1.15rem var(--era-page-bottom-safe)", display: "flex", flexDirection: "column", gap: "1.75rem" }}>
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
        <div>
          <MonoLabel tone="violet">ЭРА</MonoLabel>
          <h1 style={{ margin: "0.4rem 0 0", fontFamily: "var(--era-font-display)", fontSize: "1.85rem", lineHeight: 1.05 }}>
            {greeting()}, {user.first_name}.
          </h1>
          <p style={{ margin: "0.4rem 0 0", color: "var(--era-text-secondary)", fontSize: ".9rem" }}>
            Вот что сейчас важнее всего.
          </p>
        </div>
        <button type="button" onClick={onOpenProfile} aria-label="Открыть профиль" style={{ minWidth: 44, width: 44, height: 44, minHeight: 44, padding: 0, border: 0, borderRadius: "50%", background: "transparent", boxShadow: "none" }}>
          <Avatar firstName={user.first_name} lastName={user.last_name} />
        </button>
      </header>

      <section aria-label="Афиша ЭРА" style={{ display: "flex", flexDirection: "column", gap: ".7rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: ".75rem" }}>
          <h2 style={{ margin: 0, fontSize: "1.15rem" }}>Афиша ЭРА</h2>
          {onOpenEvents && <button type="button" className="era-btn-ghost" onClick={onOpenEvents}>Все мероприятия →</button>}
        </div>
        {featuredEvent && (
          <Card gradient style={{ padding: 0, overflow: "hidden", display: "grid" }}>
            <button
              type="button"
              onClick={onOpenEvent ? () => onOpenEvent(featuredEvent.id) : undefined}
              style={{
                display: "grid",
                gap: "0.4rem",
                padding: 0,
                border: 0,
                background: "transparent",
                textAlign: "left",
                width: "100%",
                fontWeight: 400,
              }}
            >
              <EventPoster event={featuredEvent} compact />
              <div style={{ padding: "0.75rem 0.85rem 0" }}>
                <h2 style={{ margin: 0, fontSize: "1.05rem", lineHeight: 1.3, fontWeight: 800 }}>{featuredEvent.title}</h2>
                <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-secondary)", fontSize: "0.84rem", lineHeight: 1.4 }}>
                  {formatDate(featuredEvent.event_date)} · {featuredEvent.event_time} · {featuredEvent.location}
                </p>
              </div>
            </button>
            <div style={{ padding: "0.55rem 0.85rem 0.9rem" }}>
              <AnniversaryRegistration key={featuredEvent.id} event={featuredEvent} />
            </div>
          </Card>
        )}
        {eventBoard === "loading" && <SkeletonCard />}
        {eventBoard === "error" && <EmptyState text="Афиша временно недоступна." />}
        {Array.isArray(eventBoard) && upcomingEvents.length === 0 && !featuredEvent && (
          <EmptyState text="Пока нет ближайших мероприятий." />
        )}
        {upcomingEvents.slice(0, 3).map((event) => (
          <Card key={event.id} onClick={onOpenEvent ? () => onOpenEvent(event.id) : onOpenEvents} style={{ padding: "0.75rem 0.85rem" }}>
            <strong style={{ display: "block", fontSize: "0.95rem", lineHeight: 1.3 }}>{event.title}</strong>
            <p style={{ margin: ".2rem 0 0", color: "var(--era-text-secondary)", fontSize: "0.8rem" }}>
              {formatDate(event.event_date)} · {event.event_time}
              {event.location ? ` · ${event.location}` : ""}
            </p>
          </Card>
        ))}
      </section>

      <section style={{ display: "flex", flexDirection: "column", gap: ".65rem" }}>
        <MonoLabel>Следующий шаг</MonoLabel>
        {data.next_step ? (
          <Card gradient onClick={nextStepClick} style={{ padding: "1.15rem" }}>
            <strong style={{ display: "block", fontSize: "1.15rem" }}>{data.next_step.title}</strong>
            <p style={{ margin: ".4rem 0 0", color: "var(--era-text-secondary)", fontSize: ".9rem", lineHeight: 1.5 }}>{data.next_step.description}</p>
            {nextStepClick && <span style={{ display: "block", marginTop: ".75rem", color: "var(--era-violet)", fontWeight: 800, fontSize: ".85rem" }}>{data.next_step.action_label} →</span>}
          </Card>
        ) : (
          <Card>
            <strong>Срочных действий нет</strong>
            <p style={{ margin: ".35rem 0 0", color: "var(--era-text-secondary)", fontSize: ".9rem" }}>Можно выбрать событие, задачу или возможность на свой темп.</p>
          </Card>
        )}
      </section>

      {user.features.vector && (onOpenAssessments || onOpenDevelopment) && (
        <section style={{ display: "flex", flexDirection: "column", gap: ".65rem" }}>
          <MonoLabel>Профиль</MonoLabel>
          <Card gradient onClick={onOpenAssessments ?? onOpenDevelopment} style={{ padding: "1.15rem" }}>
            <strong style={{ display: "block", fontSize: "1.1rem" }}>Узнай свой профиль · 3 мин</strong>
            <p style={{ margin: ".4rem 0 0", color: "var(--era-text-secondary)", fontSize: ".9rem", lineHeight: 1.5 }}>
              Короткий тест покажет сильные стороны и куда ты подходишь в ЭРА.
            </p>
            <span style={{ display: "block", marginTop: ".75rem", color: "var(--era-violet)", fontWeight: 800, fontSize: ".85rem" }}>
              Пройти →
            </span>
          </Card>
        </section>
      )}

      {(data.active_task || data.tasks_available_count > 0 || data.tasks_in_progress_count > 0) && (
        <section style={{ display: "flex", flexDirection: "column", gap: ".65rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: ".75rem" }}>
            <MonoLabel>Мои задачи</MonoLabel>
            {onOpenTasks && <button type="button" className="era-btn-ghost" onClick={onOpenTasks}>Все задачи →</button>}
          </div>
          {data.active_task && !nextStepIsTask ? (
            <Card onClick={onOpenTask ? () => onOpenTask(data.active_task!.id) : undefined}>
              <div style={{ display: "flex", alignItems: "center", gap: ".75rem" }}>
                <IconBubble tone="violet"><TaskIcon width={18} height={18} /></IconBubble>
                <div style={{ minWidth: 0 }}>
                  <strong style={{ display: "block" }}>{data.active_task.title}</strong>
                  <span style={{ display: "block", marginTop: ".25rem", color: "var(--era-text-secondary)", fontSize: ".82rem" }}>
                    До {formatDate(data.active_task.deadline)} · {data.active_task.points} баллов
                  </span>
                </div>
              </div>
            </Card>
          ) : (
            <Card onClick={onOpenTasks}>
              <strong>{data.tasks_in_progress_count > 0 ? `В работе: ${data.tasks_in_progress_count} задач` : `Доступно задач: ${data.tasks_available_count}`}</strong>
              <p style={{ margin: ".3rem 0 0", color: "var(--era-text-secondary)", fontSize: ".85rem" }}>Открой список и выбери, за что взяться дальше.</p>
            </Card>
          )}
        </section>
      )}

      {dailyQuote && (
        <Card style={{ borderLeft: "3px solid var(--era-violet)", padding: "1rem" }}>
          <MonoLabel>Мысль дня</MonoLabel>
          <p style={{ margin: ".45rem 0 0", lineHeight: 1.55, color: "var(--era-text-secondary)" }}>«{dailyQuote}»</p>
        </Card>
      )}

      <Card onClick={user.features.vector ? onOpenDevelopment : undefined} style={{ padding: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: ".8rem", alignItems: "center" }}>
          <div>
            <MonoLabel>Мой путь</MonoLabel>
            <strong style={{ display: "block", marginTop: ".3rem", fontSize: "1.1rem" }}>{data.growth.label}</strong>
            <span style={{ display: "block", marginTop: ".2rem", color: "var(--era-text-secondary)", fontSize: ".85rem" }}>Участник → Активный → Лидер</span>
          </div>
          {user.features.vector && <span aria-hidden="true" style={{ color: "var(--era-violet)" }}>→</span>}
        </div>
      </Card>

      <section style={{ display: "flex", flexDirection: "column", gap: ".7rem" }}>
        <MonoLabel>Ближайшее</MonoLabel>
        {nearestEvent ? (
          <PosterCard
            dark
            eyebrow={formatDate(nearestEvent.event_date)}
            title={nearestEvent.title}
            subtitle={`${nearestEvent.event_time} · ${nearestEvent.location}`}
            cta="Открыть событие"
            onClick={onOpenEvent ? () => onOpenEvent(nearestEvent.id) : onOpenEvents}
          />
        ) : data.active_task && onOpenTask ? (
          <Card onClick={() => onOpenTask(data.active_task!.id)}>
            <div style={{ display: "flex", gap: ".75rem" }}>
              <IconBubble tone="violet"><TaskIcon width={18} height={18} /></IconBubble>
              <div><strong>{data.active_task.title}</strong><p style={{ margin: ".25rem 0 0", color: "var(--era-text-secondary)" }}>До {formatDate(data.active_task.deadline)}</p></div>
            </div>
          </Card>
        ) : data.active_project && onOpenProject ? (
          <Card onClick={() => onOpenProject(data.active_project!.id)}>
            <div style={{ display: "flex", gap: ".75rem" }}>
              <IconBubble tone="orange"><ProjectsIcon width={18} height={18} /></IconBubble>
              <div><strong>{data.active_project.title}</strong><p style={{ margin: ".25rem 0 0", color: "var(--era-text-secondary)" }}>{data.active_project.status}</p></div>
            </div>
          </Card>
        ) : <EmptyState text="На ближайшее время ничего не запланировано." />}
      </section>

      <section style={{ display: "flex", flexDirection: "column", gap: ".7rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: ".75rem" }}>
          <MonoLabel>Возможности для тебя</MonoLabel>
          {onOpenCommunity && <button type="button" className="era-btn-ghost" onClick={onOpenCommunity}>Все →</button>}
        </div>
        {data.opportunities.length ? data.opportunities.slice(0, 3).map((item) => (
          <Card key={item.id} onClick={onOpenOpportunity ? () => onOpenOpportunity(item.id) : onOpenCommunity}>
            <div style={{ display: "flex", gap: ".75rem" }}>
              <IconBubble tone="magenta"><EventIcon width={18} height={18} /></IconBubble>
              <div style={{ minWidth: 0 }}>
                <strong>{item.title}</strong>
                <p style={{ margin: ".25rem 0 0", color: "var(--era-text-secondary)", fontSize: ".82rem" }}>
                  {item.expires_at ? `До ${formatDate(item.expires_at)}` : "Доступно сейчас"}
                </p>
              </div>
            </div>
          </Card>
        )) : <EmptyState text="Новых персональных возможностей пока нет." />}
      </section>

      <section style={{ display: "flex", flexDirection: "column", gap: ".65rem" }}>
        <MonoLabel>Подтверждённый результат</MonoLabel>
        <Card>
          {confirmedResult ? (
            <>
              <strong>{confirmedResult}</strong>
              <p style={{ margin: ".3rem 0 0", color: "var(--era-text-secondary)", fontSize: ".85rem" }}>Опыт сохраняется в профиле и портфолио.</p>
            </>
          ) : (
            <p style={{ margin: 0, color: "var(--era-text-secondary)", fontSize: ".9rem" }}>Первый подтверждённый результат появится после события, задачи или проекта.</p>
          )}
        </Card>
      </section>
    </div>
  );
}
