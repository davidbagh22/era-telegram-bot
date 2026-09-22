import type { ReactNode } from "react";
import { Avatar } from "../components/Avatar";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { MonoLabel } from "../components/MonoLabel";
import { PosterCard } from "../components/PosterCard";
import { Skeleton, SkeletonCard } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import { EventIcon, ProjectsIcon, TaskIcon } from "../components/icons";
import { useHome } from "../hooks/useHome";
import type { MiniAppUserSummary } from "../types/auth";

interface HomeScreenProps {
  user: MiniAppUserSummary;
  onOpenProfile?: () => void;
  onOpenProgress?: () => void;
  onOpenDevelopment?: () => void;
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
  onOpenEvents,
  onOpenEvent,
  onOpenProject,
  onOpenTask,
  onOpenCommunity,
  onOpenOpportunity,
}: HomeScreenProps) {
  const home = useHome();

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

  const nextStepClick = (() => {
    if (!data.next_step) return undefined;
    const { kind, entity_id } = data.next_step;
    if (kind === "task" && entity_id != null && onOpenTask) return () => onOpenTask(entity_id);
    if (kind === "event" && entity_id != null && onOpenEvent) return () => onOpenEvent(entity_id);
    if (kind === "project" && entity_id != null && onOpenProject) return () => onOpenProject(entity_id);
    if (kind === "opportunity" && entity_id != null && onOpenOpportunity) return () => onOpenOpportunity(entity_id);
    if (kind === "growth" && onOpenDevelopment) return onOpenDevelopment;
    return undefined;
  })();

  const confirmedResult = data.activity.completed_tasks > 0
    ? `${data.activity.completed_tasks} завершённых задач`
    : data.activity.projects > 0
      ? `${data.activity.projects} проектов в опыте`
      : data.activity.portfolio_items > 0
        ? `${data.activity.portfolio_items} подтверждённых записей`
        : null;

  return (
    <div className="era-page era-stagger" style={{ padding: "1rem 1rem var(--era-page-bottom-safe)", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
        <div>
          <MonoLabel tone="violet">ЭРА</MonoLabel>
          <h1 style={{ margin: "0.35rem 0 0", fontFamily: "var(--era-font-display)", fontSize: "1.8rem", lineHeight: 1.05 }}>
            {greeting()}, {user.first_name}.
          </h1>
          <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-secondary)", fontSize: ".9rem" }}>
            Вот что сейчас важнее всего.
          </p>
        </div>
        <button type="button" onClick={onOpenProfile} aria-label="Открыть профиль" style={{ minWidth: 44, width: 44, height: 44, minHeight: 44, padding: 0, border: 0, borderRadius: "50%", background: "transparent", boxShadow: "none" }}>
          <Avatar firstName={user.first_name} lastName={user.last_name} />
        </button>
      </header>

      <section style={{ display: "flex", flexDirection: "column", gap: ".65rem" }}>
        <MonoLabel>Следующий шаг</MonoLabel>
        {data.next_step ? (
          <Card gradient onClick={nextStepClick} style={{ padding: "1.1rem" }}>
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

      <Card onClick={onOpenDevelopment} style={{ padding: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: ".8rem", alignItems: "center" }}>
          <div>
            <MonoLabel>Мой путь</MonoLabel>
            <strong style={{ display: "block", marginTop: ".3rem", fontSize: "1.1rem" }}>{data.growth.label}</strong>
            <span style={{ display: "block", marginTop: ".2rem", color: "var(--era-text-secondary)", fontSize: ".85rem" }}>Участник → Активный → Лидер</span>
          </div>
          <span aria-hidden="true" style={{ color: "var(--era-violet)" }}>→</span>
        </div>
      </Card>

      <section style={{ display: "flex", flexDirection: "column", gap: ".7rem" }}>
        <MonoLabel>Ближайшее</MonoLabel>
        {data.nearest_event ? (
          <PosterCard
            dark
            eyebrow={formatDate(data.nearest_event.event_date)}
            title={data.nearest_event.title}
            subtitle={`${data.nearest_event.event_time} · ${data.nearest_event.location}`}
            cta="Открыть событие"
            onClick={onOpenEvent ? () => onOpenEvent(data.nearest_event!.id) : onOpenEvents}
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
