import { useCallback, useState } from "react";
import { claimTask, fetchTasks } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { PillTabs } from "../../components/PillTabs";
import { useAsync } from "../../hooks/useAsync";
import type { TaskScope } from "../../types/activity";

const SCOPES: { value: TaskScope; label: string }[] = [
  { value: "available", label: "Доступные" },
  { value: "mine", label: "Мои" },
  { value: "review", label: "На проверке" },
  { value: "completed", label: "Выполненные" },
];

export function TasksTab() {
  const [scope, setScope] = useState<TaskScope>("mine");
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchTasks(scope), [scope, refreshKey]);
  const [pendingId, setPendingId] = useState<number | null>(null);

  const handleClaim = useCallback(async (taskId: number) => {
    setPendingId(taskId);
    try {
      await claimTask(taskId);
      setRefreshKey((key) => key + 1);
    } finally {
      setPendingId(null);
    }
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <PillTabs options={SCOPES} active={scope} onChange={setScope} />

      {state.status === "loading" && (
        <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>
      )}
      {state.status === "error" && <EmptyState text="Не удалось загрузить задачи." />}
      {state.status === "ready" && state.data.length === 0 && (
        <EmptyState text="Задач в этом разделе пока нет." />
      )}
      {state.status === "ready" &&
        state.data.map((task) => (
          <Card key={task.id}>
            <strong>{task.title}</strong>
            <p style={{ margin: "0.25rem 0", color: "var(--era-text-muted)" }}>
              До {new Date(task.deadline).toLocaleDateString("ru-RU")} · {task.points} баллов
            </p>
            {scope === "available" && !task.is_joined_or_assigned && (
              <button type="button" disabled={pendingId === task.id} onClick={() => handleClaim(task.id)}>
                Хочу помочь
              </button>
            )}
            {task.can_submit && task.submit_deep_link && (
              <a href={task.submit_deep_link} target="_blank" rel="noreferrer">
                Отправить результат в боте
              </a>
            )}
          </Card>
        ))}
    </div>
  );
}
