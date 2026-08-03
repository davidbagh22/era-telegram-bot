import { useCallback, useState } from "react";
import type { CSSProperties } from "react";
import { createLeaderOpenTask, decideLeaderApplication, fetchLeaderOpenTasks } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { useAsync } from "../../hooks/useAsync";

const inputStyle = {
  fontFamily: "var(--era-font-body)",
  minHeight: "2.75rem",
  padding: "0.625rem 0.75rem",
  borderRadius: "0.75rem",
  border: "1px solid var(--era-border)",
  background: "var(--era-surface)",
  color: "var(--era-text)",
} satisfies CSSProperties;

const buttonStyle = {
  minHeight: "2.75rem",
  border: "1px solid var(--era-red)",
  borderRadius: "0.875rem",
  background: "var(--era-red)",
  color: "#fff",
  fontFamily: "var(--era-font-body)",
  fontWeight: 700,
} satisfies CSSProperties;

const secondaryButtonStyle = {
  ...buttonStyle,
  border: "1px solid var(--era-border)",
  background: "var(--era-surface)",
  color: "var(--era-text)",
} satisfies CSSProperties;

const APPLICATION_STATUS_LABELS: Record<string, string> = {
  pending: "на рассмотрении",
  accepted: "принят",
  joined: "в команде",
  rejected: "отклонён",
};

export function OpenTasksTab() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(fetchLeaderOpenTasks, [refreshKey]);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [deadline, setDeadline] = useState("");
  const [points, setPoints] = useState("10");
  const [maxParticipants, setMaxParticipants] = useState("1");
  const [formError, setFormError] = useState(false);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleCreate = useCallback(async () => {
    if (!title.trim() || !description.trim() || !deadline) {
      setFormError(true);
      return;
    }
    setFormError(false);
    setPendingKey("create");
    try {
      await createLeaderOpenTask({
        title,
        description,
        deadline: new Date(deadline).toISOString(),
        points: Number(points) || 0,
        max_participants: Number(maxParticipants) || 1,
      });
      setTitle("");
      setDescription("");
      setDeadline("");
      setPoints("10");
      setMaxParticipants("1");
      setShowForm(false);
      refresh();
    } catch {
      setFormError(true);
    } finally {
      setPendingKey(null);
    }
  }, [title, description, deadline, points, maxParticipants, refresh]);

  const handleDecide = useCallback(
    async (taskId: number, userId: number, action: "accept" | "reject") => {
      setPendingKey(`${taskId}:${userId}`);
      try {
        await decideLeaderApplication(taskId, userId, action);
        refresh();
      } finally {
        setPendingKey(null);
      }
    },
    [refresh],
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <button type="button" style={secondaryButtonStyle} onClick={() => setShowForm((value) => !value)}>
        {showForm ? "Отменить" : "Новая открытая задача"}
      </button>

      {showForm && (
        <Card>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Название"
              style={inputStyle}
            />
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Описание"
              rows={3}
              style={inputStyle}
            />
            <input
              type="datetime-local"
              value={deadline}
              onChange={(event) => setDeadline(event.target.value)}
              style={inputStyle}
            />
            <input
              type="number"
              min={0}
              max={1000}
              value={points}
              onChange={(event) => setPoints(event.target.value)}
              placeholder="Баллы"
              style={inputStyle}
            />
            <input
              type="number"
              min={1}
              max={50}
              value={maxParticipants}
              onChange={(event) => setMaxParticipants(event.target.value)}
              placeholder="Нужно помощников"
              style={inputStyle}
            />
            {formError && (
              <p style={{ color: "var(--era-error, #E5342B)", fontSize: "0.8125rem", margin: 0 }}>
                Заполните название, описание и дедлайн.
              </p>
            )}
            <button type="button" disabled={pendingKey === "create"} onClick={handleCreate} style={buttonStyle}>
              Опубликовать
            </button>
          </div>
        </Card>
      )}

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить открытые задачи." />}
      {state.status === "ready" && state.data.length === 0 && (
        <EmptyState text="Открытых задач пока нет." />
      )}
      {state.status === "ready" &&
        state.data.map((task) => (
          <Card key={task.id}>
            <strong>{task.title}</strong>
            <p style={{ margin: "0.25rem 0", color: "var(--era-text-muted)" }}>{task.description}</p>
            <p style={{ margin: "0 0 0.5rem", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
              До {new Date(task.deadline).toLocaleString("ru-RU")} · {task.points} баллов · нужно{" "}
              {task.max_participants ?? "без ограничения"}
            </p>
            {task.applications.length === 0 ? (
              <EmptyState text="Откликов пока нет." />
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {task.applications.map((application) => {
                  const key = `${task.id}:${application.user_id}`;
                  return (
                    <div
                      key={key}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        gap: "0.5rem",
                      }}
                    >
                      <span>
                        {application.first_name} {application.last_name ?? ""} —{" "}
                        {APPLICATION_STATUS_LABELS[application.status] ?? application.status}
                      </span>
                      {application.status === "pending" && (
                        <div style={{ display: "flex", gap: "0.375rem" }}>
                          <button
                            type="button"
                            disabled={pendingKey === key}
                            onClick={() => handleDecide(task.id, application.user_id, "accept")}
                          >
                            Принять
                          </button>
                          <button
                            type="button"
                            disabled={pendingKey === key}
                            onClick={() => handleDecide(task.id, application.user_id, "reject")}
                          >
                            Отклонить
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </Card>
        ))}
    </div>
  );
}
