import { fetchLeaderOverview } from "../../api/client";
import { AvatarCluster } from "../../components/AvatarCluster";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { MetricCard } from "../../components/MetricCard";
import { useAsync } from "../../hooks/useAsync";

const TASK_STATUS_LABELS: Record<string, string> = {
  new: "Новая",
  in_progress: "В работе",
  submitted: "На проверке",
  approved: "Выполнена",
  rejected: "Отклонена",
};

export function OverviewTab() {
  const state = useAsync(fetchLeaderOverview, []);

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }
  if (state.status === "error") {
    return <EmptyState text="Не удалось загрузить данные." />;
  }

  const { data } = state;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {(data.departments.length > 0 || data.directions.length > 0) && (
        <Card>
          {data.departments.length > 0 && <p style={{ margin: 0 }}>Отделы: {data.departments.join(", ")}</p>}
          {data.directions.length > 0 && (
            <p style={{ margin: data.departments.length > 0 ? "0.25rem 0 0" : 0 }}>
              Направления: {data.directions.join(", ")}
            </p>
          )}
        </Card>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "0.5rem" }}>
        <MetricCard label="Участники" value={data.participants.length} />
        <MetricCard label="Мероприятия" value={data.events.length} />
        <MetricCard label="Проекты" value={data.projects.length} />
        <MetricCard label="Мои задачи" value={data.tasks.length} />
      </div>

      <section>
        <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: "0 0 0.5rem" }}>
          Участники в контуре
        </h2>
        {data.participants.length === 0 ? (
          <EmptyState text="Участников в вашем контуре пока нет." />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <Card style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
              <div>
                <strong>{data.participants.length} в команде</strong>
                <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
                  Люди, которые сейчас входят в вашу зону ответственности.
                </p>
              </div>
              <AvatarCluster
                people={data.participants.map((participant) => ({
                  id: participant.id,
                  firstName: participant.first_name,
                  lastName: participant.last_name,
                }))}
                max={6}
                size="sm"
              />
            </Card>
            {data.participants.map((participant) => (
              <Card key={participant.id}>
                <strong>
                  {participant.first_name} {participant.last_name ?? ""}
                </strong>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: "0 0 0.5rem" }}>
          Мероприятия
        </h2>
        {data.events.length === 0 ? (
          <EmptyState text="Мероприятий пока нет." />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {data.events.map((event) => (
              <Card key={event.id}>
                <strong>{event.title}</strong>
                <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
                  {event.event_date} · {event.event_time}
                </p>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: "0 0 0.5rem" }}>
          Проекты
        </h2>
        {data.projects.length === 0 ? (
          <EmptyState text="Проектов пока нет." />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {data.projects.map((project) => (
              <Card key={project.id}>
                <strong>{project.title}</strong>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: "0 0 0.5rem" }}>
          Задачи, которые вы создали
        </h2>
        {data.tasks.length === 0 ? (
          <EmptyState text="Созданных задач пока нет." />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {data.tasks.map((task) => (
              <Card key={task.id}>
                <strong>{task.title}</strong>
                <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
                  {TASK_STATUS_LABELS[task.status] ?? task.status} · {task.points} баллов
                </p>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
