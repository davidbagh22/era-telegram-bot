import { useCallback, useState } from "react";
import { claimTask, describeActionError, fetchTasks } from "../../api/client";
import { fetchTaskDetail } from "../../api/taskDetails";
import { BottomSheet } from "../../components/BottomSheet";
import { Card } from "../../components/Card";
import { EditorialHero } from "../../components/EditorialHero";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import { StatusBadge } from "../../components/StatusBadge";
import { useAsync } from "../../hooks/useAsync";
import type { TaskItem, TaskScope } from "../../types/activity";

const SCOPES: { value: TaskScope; label: string; description: string }[] = [
  { value: "available", label: "Доступные", description: "Задачи, к которым можно присоединиться" },
  { value: "mine", label: "Мои", description: "То, что уже взято в работу" },
  { value: "review", label: "На проверке", description: "Отправленные результаты" },
  { value: "completed", label: "Выполненные", description: "История завершённых задач" },
];

const STATUS_LABELS: Record<string, string> = {
  draft: "Черновик",
  new: "Новая",
  published: "Открыт набор",
  in_progress: "В работе",
  review: "На проверке",
  completed: "Выполнена",
  overdue: "Просрочена",
  cancelled: "Отменена",
};

interface TasksTabProps {
  initialItemId?: number | null;
}

function TaskDetail({ task, onClaim, pending, error }: { task: TaskItem; onClaim: () => void; pending: boolean; error: string | null }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: ".75rem", paddingBottom: "1rem" }}>
      <button type="button" onClick={() => { window.location.hash = "#/tasks"; }} style={{ alignSelf: "flex-start" }}>← К заданиям</button>
      <EditorialHero eyebrow="Задание ЭРА" title={task.title} glow="hot">
        <div style={{ display: "flex", gap: ".45rem", flexWrap: "wrap" }}>
          <StatusBadge label={STATUS_LABELS[task.status] ?? "Статус обновлён"} tone="violet" />
          <span style={{ padding: ".3rem .55rem", borderRadius: 999, background: "var(--era-tint-gold)", color: "var(--era-gold-ink)", fontSize: ".78rem", fontWeight: 850 }}>+{task.points} баллов</span>
        </div>
      </EditorialHero>
      <Card>
        <strong>Что нужно сделать</strong>
        <p style={{ margin: ".45rem 0 0", whiteSpace: "pre-wrap", lineHeight: 1.55, color: "var(--era-text-muted)" }}>{task.description}</p>
      </Card>
      <Card style={{ padding: ".85rem" }}>
        <span style={{ color: "var(--era-text-muted)", fontSize: ".76rem" }}>СРОК</span>
        <strong style={{ display: "block", marginTop: 3 }}>{new Date(task.deadline).toLocaleString("ru-RU", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" })}</strong>
      </Card>
      {error && <p style={{ margin: 0, color: "var(--era-error)" }}>{error}</p>}
      {!task.is_joined_or_assigned && ["new", "published"].includes(task.status) && <button type="button" className="era-btn-primary" disabled={pending} onClick={onClaim}>{pending ? "Сохраняем…" : "Хочу помочь"}</button>}
      {task.can_submit && task.submit_deep_link && <a href={task.submit_deep_link} target="_blank" rel="noreferrer" className="era-btn-primary" style={{ textAlign: "center", textDecoration: "none" }}>Отправить результат в боте</a>}
    </div>
  );
}

export function TasksTab({ initialItemId }: TasksTabProps = {}) {
  const [scope, setScope] = useState<TaskScope>("mine");
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchTasks(scope), [scope, refreshKey]);
  const detail = useAsync(
    () => initialItemId ? fetchTaskDetail(initialItemId) : Promise.resolve(null),
    [initialItemId, refreshKey],
  );
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [filterOpen, setFilterOpen] = useState(false);

  const handleClaim = useCallback(async (taskId: number) => {
    setPendingId(taskId);
    setActionError(null);
    try {
      await claimTask(taskId);
      setRefreshKey((key) => key + 1);
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setPendingId(null);
    }
  }, []);

  if (initialItemId) {
    if (detail.status === "loading") return <SkeletonList count={3} />;
    if (detail.status === "error" || !detail.data) {
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: ".75rem" }}>
          <button type="button" onClick={() => { window.location.hash = "#/tasks"; }} style={{ alignSelf: "flex-start" }}>← К заданиям</button>
          <EmptyState text="Этот объект больше недоступен. Задание удалено, закрыто для вас или ссылка неверна." />
        </div>
      );
    }
    const task = detail.data;
    return <TaskDetail task={task} pending={pendingId === task.id} error={actionError} onClaim={() => void handleClaim(task.id)} />;
  }

  const scopeMeta = SCOPES.find((item) => item.value === scope) ?? SCOPES[1];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" onClick={() => setFilterOpen(true)} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>Показать: <strong>{scopeMeta.label}</strong></span><span>⌄</span>
      </button>

      {actionError && <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>}
      {state.status === "loading" && <SkeletonList count={3} />}
      {state.status === "error" && <EmptyState text="Не удалось загрузить задачи." />}
      {state.status === "ready" && state.data.length === 0 && <EmptyState text="Пока нет задач в этом разделе. Как только появится новое действие, оно будет здесь." />}
      {state.status === "ready" && state.data.map((task) => (
        <Card key={task.id}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: ".55rem", alignItems: "flex-start" }}>
            <strong>{task.title}</strong>
            <strong style={{ whiteSpace: "nowrap" }}>+{task.points}</strong>
          </div>
          <p style={{ margin: "0.3rem 0", color: "var(--era-text-muted)" }}>До {new Date(task.deadline).toLocaleDateString("ru-RU")} · {STATUS_LABELS[task.status] ?? "Статус обновлён"}</p>
          <button type="button" onClick={() => { window.location.hash = `#/tasks/${task.id}`; }} style={{ width: "100%", marginTop: ".4rem" }}>Открыть задание</button>
        </Card>
      ))}

      <BottomSheet open={filterOpen} onClose={() => setFilterOpen(false)} title="Какие задания показать?">
        <div style={{ display: "flex", flexDirection: "column", gap: ".5rem" }}>
          {SCOPES.map((option) => (
            <button key={option.value} type="button" onClick={() => { setScope(option.value); setFilterOpen(false); }} style={{ textAlign: "left", padding: ".85rem" }}>
              <strong>{option.label}</strong><span style={{ display: "block", marginTop: 3, color: "var(--era-text-muted)", fontSize: ".8rem" }}>{option.description}</span>
            </button>
          ))}
        </div>
      </BottomSheet>
    </div>
  );
}