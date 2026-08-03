import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { MetricCard } from "../components/MetricCard";
import { ProgressBar } from "../components/ProgressBar";
import { StatusBanner } from "../components/StatusBanner";
import { useHome } from "../hooks/useHome";
import type { MiniAppUserSummary } from "../types/auth";

const GROWTH_LABELS = ["Участник", "Активный", "Лидер"];

interface HomeScreenProps {
  user: MiniAppUserSummary;
}

export function HomeScreen({ user }: HomeScreenProps) {
  const home = useHome();

  if (home.status === "loading") {
    return (
      <div style={{ padding: "1.5rem", color: "var(--era-text-muted)" }}>Загрузка…</div>
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

  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <div>
        <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "1.375rem", margin: 0 }}>
          Привет, {user.first_name}
        </h1>
        <p style={{ color: "var(--era-text-muted)", margin: "0.25rem 0 0" }}>
          Ваш уровень: {data.growth.label}
        </p>
      </div>

      <ProgressBar
        currentIndex={data.growth.level_index}
        totalSteps={data.growth.level_count}
        labels={GROWTH_LABELS}
      />

      <MetricCard label="Баллы" value={data.points_balance} />

      <section>
        <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: "0 0 0.5rem" }}>
          Твой следующий шаг
        </h2>
        {data.next_step ? (
          <Card gradient>
            <strong>{data.next_step.title}</strong>
            <p style={{ margin: "0.25rem 0 0" }}>{data.next_step.description}</p>
          </Card>
        ) : (
          <EmptyState text="Сейчас нет срочных действий — загляните в «Возможности»." />
        )}
      </section>

      <section>
        <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: "0 0 0.5rem" }}>
          Ближайшее мероприятие
        </h2>
        {data.nearest_event ? (
          <Card>
            <strong>{data.nearest_event.title}</strong>
            <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
              {data.nearest_event.event_date} · {data.nearest_event.event_time} ·{" "}
              {data.nearest_event.location}
            </p>
          </Card>
        ) : (
          <EmptyState text="Вы пока не зарегистрированы ни на одно мероприятие." />
        )}
      </section>

      <section>
        <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: "0 0 0.5rem" }}>
          Активная задача
        </h2>
        {data.active_task ? (
          <Card>
            <strong>{data.active_task.title}</strong>
            <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
              До {new Date(data.active_task.deadline).toLocaleDateString("ru-RU")} ·{" "}
              {data.active_task.points} баллов
            </p>
          </Card>
        ) : (
          <EmptyState text="Нет активных задач." />
        )}
      </section>

      <section>
        <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: "0 0 0.5rem" }}>
          Активный проект
        </h2>
        {data.active_project ? (
          <Card>
            <strong>{data.active_project.title}</strong>
          </Card>
        ) : (
          <EmptyState text="Нет проектов, требующих действия." />
        )}
      </section>

      <section>
        <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: "0 0 0.5rem" }}>
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
    </div>
  );
}
