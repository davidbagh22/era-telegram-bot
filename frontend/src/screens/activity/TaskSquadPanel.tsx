import { useCallback, useState } from "react";
import { assignTaskSubtask, confirmTaskSquadPlan, describeActionError, fetchTaskSquad } from "../../api/client";
import { Card } from "../../components/Card";
import { useAsync } from "../../hooks/useAsync";
import type { TaskItem } from "../../types/activity";

const SQUAD_STATUS_LABELS: Record<string, string> = {
  forming: "Собирается",
  active: "В работе",
  completed: "Завершена",
};

const SUBTASK_STATUS_LABELS: Record<string, string> = {
  proposed: "Предложена",
  planned: "Запланирована",
  in_progress: "В работе",
  done: "Готова",
};

/**
 * ToR §12 "Task Squad": участники, роли/подзадачи, чекпоинт — reading the
 * already-built `/tasks/{id}/squad*` API that had zero frontend surface
 * before this. Only rendered when the task actually has a squad (i.e. was
 * launched as a TEAM/SOLO_OR_TEAM community mission and someone claimed it).
 */
export function TaskSquadPanel({ task }: { task: TaskItem }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchTaskSquad(task.id), [task.id, refreshKey]);
  const [busyId, setBusyId] = useState<number | "plan" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const confirmPlan = async () => {
    setBusyId("plan");
    setError(null);
    try {
      await confirmTaskSquadPlan(task.id);
      refresh();
    } catch (cause) {
      setError(describeActionError(cause));
    } finally {
      setBusyId(null);
    }
  };

  const takeSubtask = async (subtaskId: number) => {
    setBusyId(subtaskId);
    setError(null);
    try {
      // Self-assign: the backend resolves the caller from the auth token,
      // this just needs *some* assignee_id, so we can't know our own user
      // id here without extra plumbing -- surfaced instead as a plain
      // "назначить" action for the squad's responsible person/privileged
      // roles, matching the API's own permission model.
      await assignTaskSubtask(task.id, subtaskId, null);
      refresh();
    } catch (cause) {
      setError(describeActionError(cause));
    } finally {
      setBusyId(null);
    }
  };

  if (state.status === "loading") return null;
  if (state.status === "error") return null; // no squad yet (SOLO task, or not claimed) -- not an error worth surfacing
  const squad = state.data;

  return (
    <Card style={{ display: "flex", flexDirection: "column", gap: ".65rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <strong>Команда задачи</strong>
        <span style={{ fontSize: ".78rem", color: "var(--era-text-muted)" }}>{SQUAD_STATUS_LABELS[squad.status] ?? squad.status}</span>
      </div>
      <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: ".85rem" }}>
        {squad.participant_ids.length} участник{squad.participant_ids.length === 1 ? "" : squad.participant_ids.length < 5 ? "а" : "ов"}
        {task.max_people ? ` из ${task.max_people}` : ""}
        {squad.checkpoint_at ? ` · чекпоинт ${new Date(squad.checkpoint_at).toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}` : ""}
      </p>

      {squad.subtasks.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: ".4rem" }}>
          {squad.subtasks.map((subtask) => (
            <div key={subtask.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: ".5rem", padding: ".5rem .6rem", borderRadius: "var(--era-radius-md)", background: "var(--era-surface-2)" }}>
              <div style={{ minWidth: 0 }}>
                <strong style={{ fontSize: ".85rem" }}>{subtask.title}</strong>
                <div style={{ fontSize: ".75rem", color: "var(--era-text-muted)" }}>
                  {SUBTASK_STATUS_LABELS[subtask.status] ?? subtask.status}
                  {subtask.assignee_id ? " · назначена" : " · свободна"}
                </div>
              </div>
              {!subtask.assignee_id && (
                <button
                  type="button"
                  disabled={busyId === subtask.id}
                  onClick={() => void takeSubtask(subtask.id)}
                  style={{ flexShrink: 0, fontSize: ".78rem" }}
                >
                  Назначить
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {squad.status === "forming" && (
        <button type="button" disabled={busyId === "plan"} onClick={() => void confirmPlan()}>
          {busyId === "plan" ? "Сохраняем…" : "Подтвердить план"}
        </button>
      )}
      {error && <p style={{ margin: 0, color: "var(--era-error)", fontSize: ".8rem" }}>{error}</p>}
    </Card>
  );
}
