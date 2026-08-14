import { useCallback, useState } from "react";
import type { CSSProperties } from "react";
import {
  createLeaderOpenTask,
  decideLeaderApplication,
  describeActionError,
  fetchLeaderOpenTasks,
  retryTaskDelivery,
} from "../../api/client";
import { BottomSheet } from "../../components/BottomSheet";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { useAsync } from "../../hooks/useAsync";
import type { TaskDestinationKey } from "../../types/leader";

const DESTINATION_OPTIONS: { value: TaskDestinationKey; label: string }[] = [
  { value: "general", label: "Общий чат" },
  { value: "internal", label: "Внутренние связи" },
  { value: "external", label: "Внешние связи" },
  { value: "leaders", label: "Чат лидеров" },
];

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
  const [actionError, setActionError] = useState<string | null>(null);
  const [destinations, setDestinations] = useState<TaskDestinationKey[]>([]);
  const [showDestinationSheet, setShowDestinationSheet] = useState(false);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const toggleDestination = useCallback((key: TaskDestinationKey) => {
    setDestinations((previous) =>
      previous.includes(key) ? previous.filter((item) => item !== key) : [...previous, key],
    );
  }, []);

  const handleCreate = useCallback(async () => {
    if (!title.trim() || !description.trim() || !deadline) {
      setFormError(true);
      return;
    }
    setFormError(false);
    setActionError(null);
    setPendingKey("create");
    try {
      await createLeaderOpenTask({
        title,
        description,
        deadline: new Date(deadline).toISOString(),
        points: Number(points) || 0,
        max_participants: Number(maxParticipants) || 1,
        destinations,
      });
      setTitle("");
      setDescription("");
      setDeadline("");
      setPoints("10");
      setMaxParticipants("1");
      setDestinations([]);
      setShowForm(false);
      refresh();
    } catch (error) {
      // Distinct from formError above: this is a real server-side failure
      // on a form that already passed client-side validation, so reusing
      // "Заполните название, описание и дедлайн" here would be actively
      // misleading — the fields are filled in, something else went wrong.
      setActionError(describeActionError(error));
    } finally {
      setPendingKey(null);
    }
  }, [title, description, deadline, points, maxParticipants, destinations, refresh]);

  const handleDecide = useCallback(
    async (taskId: number, userId: number, action: "accept" | "reject") => {
      setPendingKey(`${taskId}:${userId}`);
      setActionError(null);
      try {
        await decideLeaderApplication(taskId, userId, action);
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setPendingKey(null);
      }
    },
    [refresh],
  );

  const handleRetry = useCallback(
    async (taskId: number, deliveryId: number) => {
      const key = `retry:${taskId}:${deliveryId}`;
      setPendingKey(key);
      setActionError(null);
      try {
        await retryTaskDelivery(taskId, deliveryId);
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
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
            <button type="button" style={secondaryButtonStyle} onClick={() => setShowDestinationSheet(true)}>
              {destinations.length === 0
                ? "Объявить в чатах (необязательно)"
                : `Объявить в чатах: ${destinations.length}`}
            </button>
            {formError && (
              <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>
                Заполните название, описание и дедлайн.
              </p>
            )}
            <button type="button" disabled={pendingKey === "create"} onClick={handleCreate} style={buttonStyle}>
              Опубликовать
            </button>
          </div>
        </Card>
      )}

      <BottomSheet open={showDestinationSheet} onClose={() => setShowDestinationSheet(false)} title="Объявить в чатах">
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <p style={{ margin: 0, fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>
            Задача уже видна в приложении всем участникам — здесь можно дополнительно отправить объявление в
            выбранные чаты.
          </p>
          {DESTINATION_OPTIONS.map((option) => (
            <label
              key={option.value}
              style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.9375rem" }}
            >
              <input
                type="checkbox"
                checked={destinations.includes(option.value)}
                onChange={() => toggleDestination(option.value)}
              />
              {option.label}
            </label>
          ))}
          <button type="button" className="era-btn-primary" onClick={() => setShowDestinationSheet(false)}>
            Готово
          </button>
        </div>
      </BottomSheet>

      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
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
            {task.deliveries.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem", marginBottom: "0.5rem" }}>
                {task.deliveries.map((delivery) => {
                  const label = DESTINATION_OPTIONS.find((o) => o.value === delivery.chat_key)?.label ?? delivery.chat_key;
                  const retryKey = `retry:${task.id}:${delivery.id}`;
                  return (
                    <div key={delivery.id} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <StatusBadge
                        label={delivery.status === "sent" ? `${label}: доставлено` : `${label}: не доставлено`}
                        tone={delivery.status === "sent" ? "violet" : "red"}
                      />
                      {delivery.status !== "sent" && (
                        <button
                          type="button"
                          disabled={pendingKey === retryKey}
                          onClick={() => handleRetry(task.id, delivery.id)}
                        >
                          Повторить
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
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
                            className="era-btn-primary"
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
