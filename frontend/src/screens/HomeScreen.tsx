import { Avatar } from "../components/Avatar";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { MetricCard } from "../components/MetricCard";
import { ProgressRing } from "../components/ProgressRing";
import { Skeleton, SkeletonCard } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import { EventIcon, OpportunitiesIcon, TaskIcon } from "../components/icons";
import { useHome } from "../hooks/useHome";
import type { MiniAppUserSummary } from "../types/auth";

interface HomeScreenProps {
  user: MiniAppUserSummary;
  /** PR 38: Home's "Посмотреть, что происходит в ЭРА" quick action —
   * Home is the "где я / что происходит" view, Activity is the fuller
   * "everything that's happening" view, so this just switches tabs
   * rather than duplicating Activity's own list here. */
  onOpenActivity?: () => void;
}

export function HomeScreen({ user, onOpenActivity }: HomeScreenProps) {
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
        <Skeleton height="2.5rem" radius="var(--era-radius-control)" />
        <Skeleton height="4.5rem" radius="var(--era-radius-card)" />
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
  const hasToday = Boolean(data.next_step || data.nearest_event || data.active_task);
  const growthPercent = data.growth.level_count <= 1 ? 1 : data.growth.level_index / (data.growth.level_count - 1);

  return (
    <div className="era-page" style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {/* Hero — "где я" в одном взгляде: аватар в кольце прогресса вместо
          отдельной плоской полоски, на фирменном градиенте вместо белого
          фона. См. docs/UI_DESIGN_SYSTEM.md "Home hero". */}
      <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true">
        <clipPath id="era-hero-wave" clipPathUnits="objectBoundingBox">
          <path d="M0,0 L1,0 L1,0.86 C0.78,0.98 0.4,0.82 0,0.95 Z" />
        </clipPath>
      </svg>
      <div
        style={{
          position: "relative",
          padding: "1.75rem 1.25rem 2.5rem",
          // A fixed dark "spotlight" moment, not a themed surface — see
          // tokens.css's --era-hero-bg comment. Deliberately the same in
          // light and dark theme.
          background: "var(--era-hero-bg)",
          color: "#fff",
          overflow: "hidden",
          clipPath: "url(#era-hero-wave)",
        }}
      >
        <div
          aria-hidden="true"
          style={{
            position: "absolute",
            inset: "-20%",
            background:
              "radial-gradient(38% 42% at 18% 18%, rgba(116,44,196,0.85), transparent 70%)," +
              "radial-gradient(46% 50% at 88% 8%, rgba(190,38,143,0.75), transparent 70%)," +
              "radial-gradient(55% 60% at 70% 78%, rgba(229,43,36,0.55), transparent 70%)",
            filter: "blur(26px)",
          }}
        />
        <div style={{ position: "relative", zIndex: 1 }}>
          <p
            style={{
              margin: "0 0 1rem",
              fontSize: "0.6875rem",
              fontWeight: 700,
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: "rgba(255,255,255,0.62)",
            }}
          >
            Сегодня в ЭРА
          </p>
          <div style={{ position: "relative", width: 92, height: 92, marginBottom: "0.75rem" }}>
            <ProgressRing percent={growthPercent} size={92} />
            <div style={{ position: "absolute", inset: 12 }}>
              <Avatar firstName={user.first_name} lastName={user.last_name} size="lg" />
            </div>
          </div>
          <h1
            style={{
              fontFamily: "var(--era-font-display)",
              fontWeight: 800,
              fontSize: "1.85rem",
              lineHeight: 1.1,
              letterSpacing: "-0.01em",
              margin: "0 0 0.5rem",
            }}
          >
            Привет, {user.first_name}
          </h1>
          <p style={{ margin: 0, fontSize: "0.8125rem", color: "rgba(255,255,255,0.72)" }}>
            Уровень <strong style={{ color: "#fff" }}>{data.growth.label}</strong> · {data.growth.level_index + 1} из{" "}
            {data.growth.level_count}
          </p>
        </div>
      </div>

      <div style={{ padding: "0 1.25rem 1.25rem", display: "flex", flexDirection: "column", gap: "1.25rem" }}>
        {/* Сегодня / ближайшее: что требует внимания прямо сейчас. */}
        <section style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <h2 style={{ fontSize: "var(--era-text-base)", color: "var(--era-text-muted)", margin: 0 }}>
            Сегодня
          </h2>
          {hasToday ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {data.next_step && (
                <Card gradient>
                  <strong>{data.next_step.title}</strong>
                  <p style={{ margin: "0.25rem 0 0" }}>{data.next_step.description}</p>
                </Card>
              )}
              {data.nearest_event && (
                <Card>
                  <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
                    <span
                      style={{
                        flexShrink: 0,
                        width: 38,
                        height: 38,
                        borderRadius: "50%",
                        background: "var(--era-tint-violet)",
                        color: "var(--era-violet)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                      }}
                    >
                      <EventIcon width={18} height={18} />
                    </span>
                    <div>
                      <strong>{data.nearest_event.title}</strong>
                      <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
                        {data.nearest_event.event_date} · {data.nearest_event.event_time} ·{" "}
                        {data.nearest_event.location}
                      </p>
                    </div>
                  </div>
                </Card>
              )}
              {data.active_task && (
                <Card>
                  <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
                    <span
                      style={{
                        flexShrink: 0,
                        width: 38,
                        height: 38,
                        borderRadius: "50%",
                        background: "var(--era-tint-red)",
                        color: "var(--era-red)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                      }}
                    >
                      <TaskIcon width={18} height={18} />
                    </span>
                    <div>
                      <strong>{data.active_task.title}</strong>
                      <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
                        Дедлайн: {new Date(data.active_task.deadline).toLocaleDateString("ru-RU")} ·{" "}
                        {data.active_task.points} баллов
                      </p>
                    </div>
                  </div>
                </Card>
              )}
            </div>
          ) : (
            <EmptyState text="Сейчас нет срочных действий — загляните в «Возможности»." />
          )}
        </section>

        {/* Моя активность: баллы/проекты/задачи/портфолио одним взглядом. */}
        <section style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <h2 style={{ fontSize: "var(--era-text-base)", color: "var(--era-text-muted)", margin: 0 }}>
            Моя активность
          </h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "0.5rem" }}>
            <MetricCard label="Баллы" value={data.activity.points} tone="violet" />
            <MetricCard label="Проекты" value={data.activity.projects} tone="red" />
            <MetricCard label="Выполнено задач" value={data.activity.completed_tasks} tone="gold" />
            <MetricCard label="В портфолио" value={data.activity.portfolio_items} tone="magenta" />
          </div>
        </section>

        {/* Возможности: 1-3 актуальные карточки. */}
        <section style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <h2 style={{ fontSize: "var(--era-text-base)", color: "var(--era-text-muted)", margin: 0 }}>
            Возможности для вас
          </h2>
          {data.opportunities.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {data.opportunities.map((opportunity) => (
                <Card key={opportunity.id}>
                  <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
                    <span
                      style={{
                        flexShrink: 0,
                        width: 38,
                        height: 38,
                        borderRadius: "50%",
                        background: "var(--era-tint-gold)",
                        color: "var(--era-gold-ink)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                      }}
                    >
                      <OpportunitiesIcon width={18} height={18} />
                    </span>
                    <div>
                      <strong>{opportunity.title}</strong>
                      <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
                        {opportunity.point_cost} баллов
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

        {onOpenActivity && (
          <button type="button" className="era-btn-primary" onClick={onOpenActivity}>
            Посмотреть, что происходит в ЭРА
          </button>
        )}
      </div>
    </div>
  );
}
