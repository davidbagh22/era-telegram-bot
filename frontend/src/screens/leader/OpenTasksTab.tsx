import { useCallback, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import {
  createLeaderOpenTask,
  decideLeaderApplication,
  deleteAdminDecisionTask,
  describeActionError,
  fetchLeaderOpenTasks,
  restoreAdminDecisionTask,
  retryTaskDelivery,
} from "../../api/client";
import { BottomSheet } from "../../components/BottomSheet";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { useAsync } from "../../hooks/useAsync";
import type { LeaderOpenTask, TaskDestinationKey } from "../../types/leader";

const DESTINATION_OPTIONS: { value: TaskDestinationKey; label: string }[] = [
  { value: "general", label: "Общий чат" },
  { value: "internal", label: "Внутренние связи" },
  { value: "external", label: "Внешние связи" },
  { value: "leaders", label: "Чат лидеров" },
];

const TASK_POINT_PRESETS = [
  { points: 40, label: "Лёгкая", description: "Небольшая понятная задача" },
  { points: 80, label: "Стандартная", description: "Обычная рабочая задача" },
  { points: 150, label: "Сложная", description: "Требует заметного вклада" },
  { points: 200, label: "Высокая ответственность", description: "Ключевая задача с серьёзным результатом" },
] as const;

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
  border: "1px solid var(--era-primary)",
  borderRadius: "0.875rem",
  background: "var(--era-primary)",
  color: "var(--era-on-primary)",
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

const DESCRIPTION_PREVIEW_LIMIT = 110;

function formatTaskDeadline(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const nowYear = new Date().getFullYear();
  const options: Intl.DateTimeFormatOptions = {
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  };
  if (date.getFullYear() !== nowYear) options.year = "numeric";
  return new Intl.DateTimeFormat("ru-RU", options).format(date);
}

function isTaskExpired(deadline: string): boolean {
  const parsed = Date.parse(deadline);
  return !Number.isNaN(parsed) && parsed < Date.now();
}

function splitTaskDescription(description: string): { preview: string; expandable: boolean } {
  const normalized = description.trim();
  if (!normalized) return { preview: "", expandable: false };
  const paragraphs = normalized.split(/\n{2,}/).map((part) => part.trim()).filter(Boolean);
  const firstParagraph = (paragraphs[0] ?? normalized).replace(/\s+/g, " ");
  const hasMoreParagraphs = paragraphs.length > 1;
  if (firstParagraph.length > DESCRIPTION_PREVIEW_LIMIT) {
    const cut = firstParagraph.slice(0, DESCRIPTION_PREVIEW_LIMIT).replace(/\s+\S*$/, "");
    return { preview: `${cut || firstParagraph.slice(0, DESCRIPTION_PREVIEW_LIMIT)}…`, expandable: true };
  }
  return { preview: firstParagraph, expandable: hasMoreParagraphs };
}

export function OpenTasksTab({
  initialOpenCreate = false,
  canRemove = false,
}: {
  initialOpenCreate?: boolean;
  canRemove?: boolean;
} = {}) {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(fetchLeaderOpenTasks, [refreshKey]);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(initialOpenCreate);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [deadline, setDeadline] = useState("");
  const [points, setPoints] = useState(80);
  const [maxParticipants, setMaxParticipants] = useState("1");
  const [formError, setFormError] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [destinations, setDestinations] = useState<TaskDestinationKey[]>([]);
  const [showDestinationSheet, setShowDestinationSheet] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState<{ id: number; title: string } | null>(null);
  const [removeReason, setRemoveReason] = useState("");
  const [undoTask, setUndoTask] = useState<{ id: number; title: string } | null>(null);
  const [expandedDescriptions, setExpandedDescriptions] = useState<Record<number, boolean>>({});
  const [showExpired, setShowExpired] = useState(false);

  const { activeTasks, expiredTasks } = useMemo(() => {
    const items = state.status === "ready" ? state.data : [];
    const active: LeaderOpenTask[] = [];
    const expired: LeaderOpenTask[] = [];
    for (const item of items) {
      if (isTaskExpired(item.deadline)) expired.push(item);
      else active.push(item);
    }
    return { activeTasks: active, expiredTasks: expired };
  }, [state]);

  const toggleDescription = useCallback((taskId: number) => {
    setExpandedDescriptions((prev) => ({ ...prev, [taskId]: !prev[taskId] }));
  }, []);

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
        points,
        max_participants: Number(maxParticipants) || 1,
        destinations,
      });
      setTitle("");
      setDescription("");
      setDeadline("");
      setPoints(80);
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

  const handleConfirmRemove = useCallback(async () => {
    if (!confirmRemove) return;
    const target = confirmRemove;
    setPendingKey(`remove:${target.id}`);
    setActionError(null);
    try {
      await deleteAdminDecisionTask(target.id, removeReason.trim() || undefined);
      setConfirmRemove(null);
      setRemoveReason("");
      setUndoTask(target);
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
      setConfirmRemove(null);
    } finally {
      setPendingKey(null);
    }
  }, [confirmRemove, removeReason, refresh]);

  const handleUndoRemove = useCallback(async () => {
    if (!undoTask) return;
    setPendingKey(`restore:${undoTask.id}`);
    setActionError(null);
    try {
      await restoreAdminDecisionTask(undoTask.id);
      setUndoTask(null);
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setPendingKey(null);
    }
  }, [undoTask, refresh]);

  const renderTaskCard = (task: LeaderOpenTask, expired: boolean) => {
    const { preview, expandable } = splitTaskDescription(task.description);
    const expanded = Boolean(expandedDescriptions[task.id]);
    return (
      <Card key={task.id} style={expired ? { opacity: 0.92 } : undefined}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "0.5rem",
            flexWrap: "wrap",
            marginBottom: "0.35rem",
          }}
        >
          <StatusBadge label={expired ? "Срок прошёл" : "Открыто"} tone={expired ? "red" : "violet"} />
          <span style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem", whiteSpace: "nowrap" }}>
            До {formatTaskDeadline(task.deadline)}
          </span>
        </div>
        <strong style={{ display: "block", fontSize: "1rem", lineHeight: 1.3, overflowWrap: "anywhere" }}>
          {task.title}
        </strong>
        <p style={{ margin: "0.25rem 0 0.4rem", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
          {task.points} баллов · нужно {task.max_participants ?? "без ограничения"}
        </p>
        {preview && (
          <div style={{ margin: "0 0 0.5rem" }}>
            <p
              style={{
                margin: 0,
                color: "var(--era-text-secondary, var(--era-text-muted))",
                fontSize: "0.875rem",
                lineHeight: 1.4,
                whiteSpace: expanded ? "pre-wrap" : "normal",
                overflowWrap: "anywhere",
              }}
            >
              {expanded ? task.description : preview}
            </p>
            {expandable && (
              <button
                type="button"
                onClick={() => toggleDescription(task.id)}
                style={{
                  marginTop: "0.25rem",
                  padding: "0.15rem 0",
                  minHeight: "auto",
                  border: "none",
                  background: "transparent",
                  color: "var(--era-accent, var(--era-primary))",
                  fontSize: "0.8125rem",
                  fontWeight: 700,
                }}
              >
                {expanded ? "Свернуть" : "Подробнее"}
              </button>
            )}
          </div>
        )}
        {task.deliveries.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem", marginBottom: "0.5rem" }}>
            {task.deliveries.map((delivery) => {
              const label = DESTINATION_OPTIONS.find((o) => o.value === delivery.chat_key)?.label ?? "Чат";
              const retryKey = `retry:${task.id}:${delivery.id}`;
              return (
                <div key={delivery.id} style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
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
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", marginTop: "0.25rem", flexWrap: "wrap" }}>
            <span style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>Откликов пока нет.</span>
            {canRemove && (
              <button
                type="button"
                data-testid={`open-task-remove-${task.id}`}
                disabled={pendingKey === `remove:${task.id}`}
                onClick={() => {
                  setActionError(null);
                  setRemoveReason("");
                  setConfirmRemove({ id: task.id, title: task.title });
                }}
              >
                Убрать
              </button>
            )}
          </div>
        ) : (
          <>
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
                      flexWrap: "wrap",
                    }}
                  >
                    <span style={{ minWidth: 0, overflowWrap: "anywhere" }}>
                      {application.first_name} {application.last_name ?? ""} —{" "}
                      {APPLICATION_STATUS_LABELS[application.status] ?? "Статус обновлён"}
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
            {canRemove && (
              <div style={{ marginTop: "0.625rem", display: "flex", justifyContent: "flex-end" }}>
                <button
                  type="button"
                  data-testid={`open-task-remove-${task.id}`}
                  disabled={pendingKey === `remove:${task.id}`}
                  onClick={() => {
                    setActionError(null);
                    setRemoveReason("");
                    setConfirmRemove({ id: task.id, title: task.title });
                  }}
                >
                  Убрать
                </button>
              </div>
            )}
          </>
        )}
      </Card>
    );
  };

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
            <div style={{ display: "flex", flexDirection: "column", gap: "0.45rem" }}>
              <strong style={{ fontSize: "0.875rem" }}>Сложность и баллы</strong>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.5rem" }}>
                {TASK_POINT_PRESETS.map((preset) => {
                  const selected = points === preset.points;
                  return (
                    <button
                      key={preset.points}
                      type="button"
                      onClick={() => setPoints(preset.points)}
                      aria-pressed={selected}
                      style={{
                        minHeight: "4.5rem",
                        padding: "0.65rem",
                        textAlign: "left",
                        borderRadius: "0.75rem",
                        border: selected ? "1px solid var(--era-violet)" : "1px solid var(--era-border)",
                        background: selected ? "var(--era-tint-violet)" : "var(--era-surface)",
                        color: "var(--era-text)",
                      }}
                    >
                      <strong style={{ display: "block" }}>{preset.label} · {preset.points}</strong>
                      <span style={{ display: "block", marginTop: "0.2rem", color: "var(--era-text-muted)", fontSize: "0.75rem" }}>
                        {preset.description}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
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
        <p role="alert" style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}

      {undoTask && (
        <Card style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
          <div style={{ minWidth: 0 }}>
            <strong style={{ display: "block", fontSize: "0.875rem" }}>Задача убрана</strong>
            <span style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
              {undoTask.title} · записано в аудит
            </span>
          </div>
          <button
            type="button"
            disabled={pendingKey === `restore:${undoTask.id}`}
            onClick={() => void handleUndoRemove()}
          >
            {pendingKey === `restore:${undoTask.id}` ? "Возвращаем…" : "Вернуть"}
          </button>
        </Card>
      )}

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить открытые задачи." />}
      {state.status === "ready" && state.data.length === 0 && (
        <EmptyState text="Открытых задач пока нет." />
      )}
      {state.status === "ready" && activeTasks.length > 0 && (
        <div data-testid="active-tasks-section" style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {activeTasks.map((task) => renderTaskCard(task, false))}
        </div>
      )}
      {state.status === "ready" && activeTasks.length === 0 && expiredTasks.length > 0 && (
        <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.875rem" }}>
          Активных открытых задач сейчас нет. Ниже задачи, срок которых уже прошёл.
        </p>
      )}
      {state.status === "ready" && expiredTasks.length > 0 && (
        <div data-testid="expired-tasks-section" style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <button
            type="button"
            aria-expanded={activeTasks.length === 0 ? true : showExpired}
            onClick={() => setShowExpired((open) => !open)}
            style={{
              ...secondaryButtonStyle,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              width: "100%",
              padding: "0.625rem 0.875rem",
            }}
          >
            <span>Срок прошёл · {expiredTasks.length}</span>
            <span style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem", fontWeight: 600 }}>
              {activeTasks.length === 0 || showExpired ? "Скрыть" : "Показать"}
            </span>
          </button>
          {(activeTasks.length === 0 || showExpired) &&
            expiredTasks.map((task) => renderTaskCard(task, true))}
        </div>
      )}

      <BottomSheet
        open={confirmRemove !== null}
        onClose={() => {
          if (!pendingKey?.startsWith("remove:")) setConfirmRemove(null);
        }}
        title="Убрать задачу?"
      >
        {confirmRemove && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <strong style={{ fontSize: "0.95rem" }}>{confirmRemove.title}</strong>
            <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.85rem" }}>
              Задача исчезнет из списка и у участников. Действие запишется в журнал аудита, его можно сразу отменить.
              Задачу с непроверенными ответами участников убрать нельзя.
            </p>
            <input
              value={removeReason}
              onChange={(event) => setRemoveReason(event.target.value)}
              placeholder="Причина (необязательно)"
              maxLength={500}
              style={inputStyle}
            />
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.5rem" }}>
              <button
                type="button"
                disabled={pendingKey === `remove:${confirmRemove.id}`}
                onClick={() => setConfirmRemove(null)}
              >
                Отмена
              </button>
              <button
                type="button"
                className="era-btn-primary"
                disabled={pendingKey === `remove:${confirmRemove.id}`}
                onClick={() => void handleConfirmRemove()}
              >
                {pendingKey === `remove:${confirmRemove.id}` ? "Убираем…" : "Убрать задачу"}
              </button>
            </div>
          </div>
        )}
      </BottomSheet>
    </div>
  );
}
