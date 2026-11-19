import { useEffect, useState } from "react";
import { fetchDailyQuote, fetchEvents } from "../api/client";
import { Avatar } from "../components/Avatar";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { MonoLabel } from "../components/MonoLabel";
import { OrbitNavigator, type OrbitNodeKey } from "../components/OrbitNavigator";
import { LoadingRegion, Skeleton, SkeletonCard } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import { TypographyFeedCard } from "../components/TypographyFeedCard";
import { useHome } from "../hooks/useHome";
import { useMotionPreference } from "../motion/MotionPreference";
import type { EventItem } from "../types/activity";
import type { MiniAppUserSummary } from "../types/auth";
import { formatFeedDateLine, formatProjectFeedDate } from "../utils/feedDate";
import { displayProjectTitle } from "./projects/displayTitle";

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
  onOpenProjects?: () => void;
}

function greeting() {
  const hour = new Date().getHours();
  if (hour < 5) return "Доброй ночи";
  if (hour < 12) return "Доброе утро";
  if (hour < 18) return "Добрый день";
  return "Добрый вечер";
}

export function HomeScreen({
  user,
  onOpenProfile,
  onOpenProgress,
  onOpenDevelopment,
  onOpenAssessments,
  onOpenEvents,
  onOpenEvent,
  onOpenProject,
  onOpenTask,
  onOpenTasks,
  onOpenCommunity: _onOpenCommunity,
  onOpenOpportunity,
  onOpenProjects: _onOpenProjects,
}: HomeScreenProps) {
  void _onOpenCommunity;
  void _onOpenProjects;
  const home = useHome();
  const { liveBackground, toggleLiveBackground } = useMotionPreference();
  const [viewMode, setViewMode] = useState<"orbit" | "list">(() => {
    try { return localStorage.getItem("era.orbit.view") === "list" ? "list" : "orbit"; } catch { return "orbit"; }
  });
  const [dailyQuote, setDailyQuote] = useState("");
  const [eventBoard, setEventBoard] = useState<EventItem[] | "loading" | "error">("loading");
  const [eventsTick, setEventsTick] = useState(0);

  useEffect(() => {
    let active = true;
    setEventBoard("loading");
    void fetchEvents("all").then((events) => {
      if (active) {
        setEventBoard(
          events.filter((event) =>
            ["approved", "published", "registration_open", "registration_closed"].includes(event.status),
          ),
        );
      }
    }).catch(() => {
      if (active) setEventBoard("error");
    });
    return () => {
      active = false;
    };
  }, [eventsTick]);

  useEffect(() => {
    let active = true;
    void fetchDailyQuote().then((item) => {
      if (active) setDailyQuote(item.text);
    }).catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  if (home.status === "loading") {
    return (
      <div className="era-page">
        <LoadingRegion
          label="Загрузка орбиты"
          style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: "1rem" }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <Skeleton width={44} height={44} radius="50%" />
            <div style={{ flex: 1 }}><Skeleton height="1.1rem" width="58%" /></div>
          </div>
          <SkeletonCard />
          <SkeletonCard />
        </LoadingRegion>
      </div>
    );
  }

  if (home.status === "error") {
    return (
      <StatusBanner
        title="Не получилось загрузить орбиту"
        description="Проверь соединение и попробуй ещё раз."
        actionLabel="Обновить"
        onAction={home.reload}
      />
    );
  }

  const { data } = home;
  const featuredEvent = data.featured_event;

  const upcomingEvents = Array.isArray(eventBoard)
    ? eventBoard.filter((event) => event.id !== featuredEvent?.id)
    : [];

  const nearestCards: EventItem[] = [];
  if (featuredEvent) nearestCards.push(featuredEvent);
  for (const event of upcomingEvents) {
    if (nearestCards.length >= 3) break;
    nearestCards.push(event);
  }

  const nextStepClick = (() => {
    if (!data.next_step) return undefined;
    const { kind, entity_id } = data.next_step;
    if (kind === "task" && entity_id != null && onOpenTask) return () => onOpenTask(entity_id);
    if (kind === "event" && entity_id != null && onOpenEvent) return () => onOpenEvent(entity_id);
    if (kind === "project" && entity_id != null && onOpenProject) return () => onOpenProject(entity_id);
    if (kind === "opportunity" && entity_id != null && onOpenOpportunity) return () => onOpenOpportunity(entity_id);
    if (kind === "growth" && onOpenProgress) return onOpenProgress;
    return undefined;
  })();

  const nextStepRepeatsNearest = data.next_step?.kind === "event"
    && data.next_step.entity_id != null
    && nearestCards.some((event) => event.id === data.next_step?.entity_id);

  const handleOrbitNode = (node: OrbitNodeKey) => {
    if (node === "people") {
      if (window.location.hash !== "#/people") window.location.hash = "#/people";
      return;
    }
    if (node === "events") {
      onOpenEvents?.();
      return;
    }
    if (node === "ideas") {
      if (window.location.hash !== "#/ideas") window.location.hash = "#/ideas";
      return;
    }
    if (window.location.hash !== "#/teams") window.location.hash = "#/teams";
  };

  return (
    <div
      className="era-page era-stagger"
      style={{
        padding: "1.15rem 1.15rem var(--era-page-bottom-safe)",
        display: "flex",
        flexDirection: "column",
        gap: "1.5rem",
      }}
    >
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
        <div style={{ minWidth: 0 }}>
          <MonoLabel tone="violet">ЭРА</MonoLabel>
          <h1 style={{ margin: "0.35rem 0 0", fontFamily: "var(--era-font-display)", fontSize: "1.55rem", lineHeight: 1.08 }}>
            {greeting()}, {user.first_name}
          </h1>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.45rem", flexShrink: 0 }}>
          <button
            type="button"
            onClick={toggleLiveBackground}
            aria-pressed={liveBackground}
            aria-label={liveBackground ? "Пауза живого фона" : "Включить живой фон"}
            style={{
              minHeight: 44,
              minWidth: 44,
              padding: "0.35rem 0.55rem",
              borderRadius: "var(--era-radius-pill)",
              fontSize: "0.72rem",
              fontWeight: 700,
              border: "1px solid var(--era-border)",
              background: "var(--era-glass)",
              color: "var(--era-text-secondary)",
            }}
          >
            {liveBackground ? "⏸" : "▶"}
          </button>
          <button
            type="button"
            onClick={onOpenProfile}
            aria-label="Открыть профиль"
            style={{
              minWidth: 44,
              width: 44,
              height: 44,
              minHeight: 44,
              padding: 0,
              border: 0,
              borderRadius: "50%",
              background: "transparent",
              boxShadow: "none",
            }}
          >
            <Avatar firstName={user.first_name} lastName={user.last_name} />
          </button>
        </div>
      </header>

      <section aria-label="Твоя орбита" style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem" }}>
          <h2 style={{ margin: 0, fontFamily: "var(--era-font-display)", fontSize: "1.35rem" }}>Твоя орбита</h2>
          <div
            role="group"
            aria-label="Вид орбиты"
            style={{
              display: "inline-flex",
              padding: "0.2rem",
              borderRadius: "var(--era-radius-pill)",
              border: "1px solid var(--era-border)",
              background: "var(--era-surface)",
            }}
          >
            {(["orbit", "list"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                aria-pressed={viewMode === mode}
                onClick={() => {
                  setViewMode(mode);
                  try { localStorage.setItem("era.orbit.view", mode); } catch { /* private mode */ }
                }}
                style={{
                  minHeight: 36,
                  padding: "0.3rem 0.7rem",
                  border: "none",
                  borderRadius: "var(--era-radius-pill)",
                  background: viewMode === mode ? "var(--era-selected)" : "transparent",
                  color: viewMode === mode ? "var(--era-cyan)" : "var(--era-text-secondary)",
                  fontSize: "0.78rem",
                  fontWeight: 700,
                }}
              >
                {mode === "orbit" ? "Орбита" : "Список"}
              </button>
            ))}
          </div>
        </div>

        {viewMode === "orbit" ? (
          <OrbitNavigator onSelect={handleOrbitNode} />
        ) : (
          <div style={{ display: "grid", gap: "0.55rem" }}>
            {(
              [
                { key: "people" as const, label: "Люди", hint: "Участники и профили" },
                { key: "events" as const, label: "События", hint: "Афиша и записи" },
                { key: "ideas" as const, label: "Идеи", hint: "Предложить проект" },
                { key: "teams" as const, label: "Команды", hint: "Проектные команды" },
              ]
            ).map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => handleOrbitNode(item.key)}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: "0.75rem",
                  padding: "0.9rem 1rem",
                  borderRadius: "var(--era-radius-lg)",
                  border: "1px solid var(--era-border)",
                  background: "var(--era-glass)",
                  textAlign: "left",
                }}
              >
                <span>
                  <strong style={{ display: "block" }}>{item.label}</strong>
                  <span style={{ color: "var(--era-text-faint)", fontSize: "0.8rem" }}>{item.hint}</span>
                </span>
                <span aria-hidden="true" style={{ color: "var(--era-cyan)" }}>→</span>
              </button>
            ))}
          </div>
        )}
      </section>

      {!nextStepRepeatsNearest && (
        <section aria-label="Следующий шаг" style={{ display: "flex", flexDirection: "column", gap: ".65rem" }}>
          <MonoLabel>Следующий шаг</MonoLabel>
          {data.next_step ? (
            <Card gradient onClick={nextStepClick} style={{ padding: "1.15rem" }}>
              <strong style={{ display: "block", fontSize: "1.1rem" }}>{data.next_step.title}</strong>
              <p style={{ margin: ".4rem 0 0", color: "var(--era-text-secondary)", fontSize: ".9rem", lineHeight: 1.5 }}>
                {data.next_step.description}
              </p>
              {nextStepClick && (
                <span style={{ display: "block", marginTop: ".75rem", color: "var(--era-cyan)", fontWeight: 800, fontSize: ".85rem" }}>
                  {data.next_step.action_label} →
                </span>
              )}
            </Card>
          ) : (
            <Card onClick={onOpenEvents}>
              <strong>Выбери событие или предложи идею</strong>
              <p style={{ margin: ".35rem 0 0", color: "var(--era-text-secondary)", fontSize: ".9rem" }}>
                Первый шаг в орбите — живое участие.
              </p>
            </Card>
          )}
        </section>
      )}

      <section aria-label="Ближайшее" style={{ display: "flex", flexDirection: "column", gap: ".7rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: ".75rem" }}>
          <MonoLabel>Ближайшее</MonoLabel>
          {onOpenEvents && (
            <button type="button" className="era-btn-ghost" onClick={onOpenEvents}>
              Афиша →
            </button>
          )}
        </div>
        {eventBoard === "loading" && (
          <LoadingRegion label="Загрузка ближайшего">
            <SkeletonCard />
          </LoadingRegion>
        )}
        {eventBoard === "error" && (
          <EmptyState
            title="Расписание временно недоступно"
            text="Проверь соединение и обнови список."
            actionLabel="Обновить"
            onAction={() => setEventsTick((value) => value + 1)}
          />
        )}
        {Array.isArray(eventBoard) && nearestCards.length === 0 && (
          data.active_project && onOpenProject ? (
            <TypographyFeedCard
              title={displayProjectTitle(data.active_project.title)}
              dateLine={formatProjectFeedDate({
                proposedDate: data.active_project.proposed_date,
                proposedTime: data.active_project.proposed_time,
                dateIsTentative: data.active_project.date_is_tentative,
              })}
              onClick={() => onOpenProject(data.active_project!.id)}
            />
          ) : data.active_task && onOpenTask ? (
            <Card onClick={() => onOpenTask(data.active_task!.id)}>
              <strong>{data.active_task.title}</strong>
              <p style={{ margin: ".25rem 0 0", color: "var(--era-text-secondary)" }}>Открыть задание</p>
            </Card>
          ) : (
            <EmptyState text="Пока нет ближайших мероприятий." />
          )
        )}
        {nearestCards.map((event) => (
          <TypographyFeedCard
            key={event.id}
            title={event.title}
            dateLine={formatFeedDateLine({ date: event.event_date, time: event.event_time, endTime: event.end_time })}
            onClick={onOpenEvent ? () => onOpenEvent(event.id) : onOpenEvents}
          />
        ))}
      </section>

      {dailyQuote && (
        <Card style={{ borderLeft: "3px solid var(--era-primary)", padding: "1rem" }}>
          <MonoLabel>Новое</MonoLabel>
          <p style={{ margin: ".45rem 0 0", lineHeight: 1.55, color: "var(--era-text-secondary)" }}>«{dailyQuote}»</p>
        </Card>
      )}

      {user.features.vector && onOpenDevelopment && (
        <Card onClick={onOpenDevelopment} style={{ padding: "1.05rem" }}>
          <MonoLabel>Мой вектор</MonoLabel>
          <strong style={{ display: "block", marginTop: ".3rem" }}>Интересы и направление роста</strong>
          <p style={{ margin: ".3rem 0 0", color: "var(--era-text-secondary)", fontSize: ".85rem" }}>
            Личные ответы остаются в вашем профиле.
          </p>
          <span style={{ display: "block", marginTop: ".55rem", color: "var(--era-cyan)", fontWeight: 800, fontSize: ".85rem" }}>
            Открыть мой вектор →
          </span>
        </Card>
      )}

      {user.features.vector && onOpenAssessments && (
        <Card gradient onClick={onOpenAssessments} style={{ padding: "1.05rem" }}>
          <strong style={{ display: "block", fontSize: "1.05rem" }}>Узнай свой профиль · 3 мин</strong>
          <span style={{ display: "block", marginTop: ".55rem", color: "var(--era-cyan)", fontWeight: 800, fontSize: ".85rem" }}>
            Пройти →
          </span>
        </Card>
      )}

      {(data.tasks_available_count > 0 || data.tasks_in_progress_count > 0 || data.active_task) && onOpenTasks && (
        <Card onClick={onOpenTasks}>
          <strong>
            {data.tasks_in_progress_count > 0
              ? `В работе: ${data.tasks_in_progress_count}`
              : `Доступно задач: ${data.tasks_available_count}`}
          </strong>
          <p style={{ margin: ".3rem 0 0", color: "var(--era-text-secondary)", fontSize: ".85rem" }}>
            Открыть задания
          </p>
        </Card>
      )}
    </div>
  );
}
