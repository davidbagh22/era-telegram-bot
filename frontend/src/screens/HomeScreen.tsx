import type { ReactNode } from "react";
import { Avatar } from "../components/Avatar";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { MetricCard } from "../components/MetricCard";
import { ProgressRing } from "../components/ProgressRing";
import { Skeleton, SkeletonCard } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import { CommunityIcon, EventIcon, OpportunitiesIcon, ProjectsIcon, TaskIcon } from "../components/icons";
import { useHome } from "../hooks/useHome";
import type { MiniAppUserSummary } from "../types/auth";

interface HomeScreenProps {
  user: MiniAppUserSummary;
  onOpenEvents?: () => void;
  onOpenCommunity?: () => void;
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleDateString("ru-RU");
}

export function HomeScreen({ user, onOpenEvents, onOpenCommunity }: HomeScreenProps) {
  const home = useHome();

  if (home.status === "loading") {
    return (
      <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <Avatar firstName={user.first_name} lastName={user.last_name} />
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "0.375rem" }}>
            <Skeleton height="1.125rem" width="60%" />
            <Skeleton height="0.75rem" width="40%" />
          </div>
        </div>
        <Skeleton height="11rem" radius="var(--era-radius-card)" />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (home.status === "error") {
    return (
      <StatusBanner
        title="Не удалось загрузить данные"
        description="Потяните вниз, чтобы обновить страницу, или откройте ЭРА заново."
      />
    );
  }

  const { data } = home;
  const growthPercent = data.growth.level_count <= 1 ? 1 : data.growth.level_index / (data.growth.level_count - 1);
  const hasAttention = Boolean(data.next_step || data.nearest_event || data.active_task || data.active_project);

  return (
    <div
      className="era-page"
      style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}
    >
      <Card
        gradient
        style={{
          position: "relative",
          overflow: "hidden",
          minHeight: 214,
          padding: "1.25rem",
        }}
      >
        <div
          aria-hidden="true"
          style={{
            position: "absolute",
            right: -52,
            top: -58,
            width: 190,
            height: 190,
            borderRadius: "50%",
            border: "1px solid rgba(255,255,255,0.16)",
            background:
              "radial-gradient(circle at 34% 34%, rgba(255,255,255,0.2), rgba(255,255,255,0.03) 60%, transparent 72%)",
          }}
        />
        <div
          aria-hidden="true"
          style={{
            position: "absolute",
            left: "1rem",
            right: "1rem",
            bottom: "1rem",
            height: 2,
            borderRadius: 999,
            background: "linear-gradient(90deg, rgba(255,255,255,0.1), rgba(255,255,255,0.62), rgba(255,255,255,0.1))",
          }}
        />
        <div style={{ position: "relative", display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem" }}>
            <div>
              <p
                style={{
                  margin: "0 0 0.35rem",
                  color: "rgba(255,255,255,0.66)",
                  fontSize: "var(--era-text-xs)",
                  fontWeight: 800,
                  textTransform: "uppercase",
                }}
              >
                ЭРА сегодня
              </p>
              <h1 style={{ margin: 0, fontSize: "var(--era-text-3xl)", lineHeight: 1.08 }}>
                {user.first_name}, держим темп
              </h1>
            </div>
            <div style={{ position: "relative", width: 84, height: 84, flexShrink: 0 }}>
              <ProgressRing percent={growthPercent} size={84} />
              <div style={{ position: "absolute", inset: 11 }}>
                <Avatar firstName={user.first_name} lastName={user.last_name} size="lg" />
              </div>
            </div>
          </div>
          <div>
            <p style={{ margin: 0, color: "rgba(255,255,255,0.72)" }}>
              Уровень <strong style={{ color: "#fff" }}>{data.growth.label}</strong>
            </p>
            <p style={{ margin: "0.25rem 0 0", color: "rgba(255,255,255,0.72)" }}>
              Баланс: <strong style={{ color: "#fff" }}>{data.points_balance}</strong> баллов
            </p>
          </div>
        </div>
      </Card>

      <section style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <h2 style={{ fontSize: "var(--era-text-xl)", margin: 0 }}>Требует внимания</h2>
        {hasAttention ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {data.next_step && (
              <Card gradient>
                <strong>{data.next_step.title}</strong>
                <p style={{ margin: "0.35rem 0 0", color: "rgba(255,255,255,0.78)" }}>
                  {data.next_step.description}
                </p>
              </Card>
            )}
            {data.nearest_event && (
              <Card>
                <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
                  <IconBubble tone="violet">
                    <EventIcon width={18} height={18} />
                  </IconBubble>
                  <div>
                    <strong>{data.nearest_event.title}</strong>
                    <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
                      {data.nearest_event.event_date} · {data.nearest_event.event_time} · {data.nearest_event.location}
                    </p>
                  </div>
                </div>
              </Card>
            )}
            {data.active_task && (
              <Card>
                <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
                  <IconBubble tone="red">
                    <TaskIcon width={18} height={18} />
                  </IconBubble>
                  <div>
                    <strong>{data.active_task.title}</strong>
                    <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
                      Дедлайн: {formatDate(data.active_task.deadline)} · {data.active_task.points} баллов
                    </p>
                  </div>
                </div>
              </Card>
            )}
            {data.active_project && (
              <Card>
                <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
                  <IconBubble tone="gold">
                    <ProjectsIcon width={18} height={18} />
                  </IconBubble>
                  <div>
                    <strong>{data.active_project.title}</strong>
                    <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
                      Статус: {data.active_project.status}
                    </p>
                  </div>
                </div>
              </Card>
            )}
          </div>
        ) : (
          <EmptyState text="Срочных действий нет. Можно выбрать событие или посмотреть возможности сообщества." />
        )}
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.75rem" }}>
        <MetricCard label="Баллы" value={data.activity.points} tone="violet" />
        <MetricCard label="Проекты" value={data.activity.projects} tone="red" />
        <MetricCard label="Задачи" value={data.activity.completed_tasks} tone="gold" />
        <MetricCard label="Портфолио" value={data.activity.portfolio_items} tone="magenta" />
      </section>

      <section style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "center" }}>
          <h2 style={{ fontSize: "var(--era-text-xl)", margin: 0 }}>Для тебя</h2>
          {onOpenCommunity && (
            <button type="button" onClick={onOpenCommunity} style={{ minHeight: "2.35rem", padding: "0.45rem 0.8rem" }}>
              Все
            </button>
          )}
        </div>
        {data.opportunities.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {data.opportunities.slice(0, 2).map((opportunity) => (
              <Card key={opportunity.id}>
                <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
                  <IconBubble tone="gold">
                    <OpportunitiesIcon width={18} height={18} />
                  </IconBubble>
                  <div>
                    <strong>{opportunity.title}</strong>
                    <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
                      {opportunity.point_cost} баллов
                      {opportunity.expires_at ? ` · до ${opportunity.expires_at.slice(0, 10)}` : ""}
                    </p>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        ) : (
          <EmptyState text="Подходящих возможностей пока нет." />
        )}
      </section>

      {(onOpenEvents || onOpenCommunity) && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.75rem" }}>
          {onOpenEvents && (
            <button type="button" className="era-btn-primary" onClick={onOpenEvents}>
              События
            </button>
          )}
          {onOpenCommunity && (
            <button type="button" onClick={onOpenCommunity}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
                <CommunityIcon width={18} height={18} />
                Сообщество
              </span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function IconBubble({ children, tone }: { children: ReactNode; tone: "violet" | "red" | "gold" }) {
  const styleByTone = {
    violet: { background: "var(--era-tint-violet)", color: "var(--era-violet)" },
    red: { background: "var(--era-tint-red)", color: "var(--era-red)" },
    gold: { background: "var(--era-tint-gold)", color: "var(--era-gold-ink)" },
  }[tone];
  return (
    <span
      style={{
        flexShrink: 0,
        width: 38,
        height: 38,
        borderRadius: "50%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        ...styleByTone,
      }}
    >
      {children}
    </span>
  );
}
