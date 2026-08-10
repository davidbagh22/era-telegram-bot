import { Avatar } from "../components/Avatar";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { MetricCard } from "../components/MetricCard";
import { ProgressBar } from "../components/ProgressBar";
import { Skeleton, SkeletonCard } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import { useHome } from "../hooks/useHome";
import type { MiniAppUserSummary } from "../types/auth";

const GROWTH_LABELS = ["Участник", "Активный", "Лидер"];

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

  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {/* Верх: кто я, какой уровень, прогресс — see brief section 6. */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
        <Avatar firstName={user.first_name} lastName={user.last_name} />
        <div>
          <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "var(--era-text-2xl)", margin: 0 }}>
            Привет, {user.first_name}
          </h1>
          <p style={{ color: "var(--era-text-muted)", margin: "0.25rem 0 0" }}>
            Ваш уровень: {data.growth.label}
          </p>
        </div>
      </div>

      <ProgressBar
        currentIndex={data.growth.level_index}
        totalSteps={data.growth.level_count}
        labels={GROWTH_LABELS}
      />

      {/* Сегодня / ближайшее: что требует внимания прямо сейчас. */}
      <section style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <h2 style={{ fontSize: "var(--era-text-base)", color: "var(--era-text-muted)", margin: 0 }}>
          Сегодня
        </h2>
        {hasToday ? (
          <>
            {data.next_step && (
              <Card gradient>
                <strong>{data.next_step.title}</strong>
                <p style={{ margin: "0.25rem 0 0" }}>{data.next_step.description}</p>
              </Card>
            )}
            {data.nearest_event && (
              <Card>
                <p style={{ margin: 0, fontSize: "var(--era-text-xs)", color: "var(--era-text-muted)" }}>
                  📅 Ближайшее мероприятие
                </p>
                <strong>{data.nearest_event.title}</strong>
                <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
                  {data.nearest_event.event_date} · {data.nearest_event.event_time} ·{" "}
                  {data.nearest_event.location}
                </p>
              </Card>
            )}
            {data.active_task && (
              <Card>
                <p style={{ margin: 0, fontSize: "var(--era-text-xs)", color: "var(--era-text-muted)" }}>
                  ✅ Задача
                </p>
                <strong>{data.active_task.title}</strong>
                <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
                  Дедлайн: {new Date(data.active_task.deadline).toLocaleDateString("ru-RU")} ·{" "}
                  {data.active_task.points} баллов
                </p>
              </Card>
            )}
          </>
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
          <MetricCard label="Баллы" value={data.activity.points} />
          <MetricCard label="Проекты" value={data.activity.projects} />
          <MetricCard label="Выполнено задач" value={data.activity.completed_tasks} />
          <MetricCard label="В портфолио" value={data.activity.portfolio_items} />
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
                <strong>{opportunity.title}</strong>
                <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
                  {opportunity.point_cost} баллов
                </p>
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
  );
}
