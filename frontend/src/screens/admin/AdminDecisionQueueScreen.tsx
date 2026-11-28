import { useCallback, useState } from "react";
import {
  deleteAdminDecisionItem,
  deleteAdminDecisionTask,
  describeActionError,
  fetchAdminDecisionQueue,
  restoreAdminDecisionItem,
  restoreAdminDecisionTask,
} from "../../api/client";
import { BottomSheet } from "../../components/BottomSheet";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { useAsync } from "../../hooks/useAsync";
import type { DecisionQueueItem, DecisionQueueTask } from "../../types/admin";

const TASK_REASON_LABELS: Record<string, string> = {
  overdue: "Просрочена",
  review: "На проверке",
  pending_submission: "Есть ответ на проверке",
  blocker: "Есть блокер",
};

const DECISION_STATUS_LABELS: Record<string, string> = {
  open: "Открыто",
  in_progress: "В работе",
  deferred: "Отложено",
};

type PendingDeleteTarget =
  | { kind: "decision"; item: DecisionQueueItem }
  | { kind: "task"; item: DecisionQueueTask };

type UndoItem = {
  kind: "decision" | "task";
  id: number;
  label: string;
};

function formatDate(value: string | null): string {
  if (!value) return "Без срока";
  const iso = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Без срока";
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: "Asia/Yerevan",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

interface AdminDecisionQueueScreenProps {
  onBack: () => void;
  onOpenTaskReview: () => void;
  onOpenNativeTaskQueue?: () => void;
  onChanged?: () => void;
}

export function AdminDecisionQueueScreen({
  onBack,
  onOpenTaskReview,
  onOpenNativeTaskQueue,
  onChanged,
}: AdminDecisionQueueScreenProps) {
  const [refreshKey, setRefreshKey] = useState(0);
  const queue = useAsync(() => fetchAdminDecisionQueue(), [refreshKey]);
  const [target, setTarget] = useState<PendingDeleteTarget | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [undoItem, setUndoItem] = useState<UndoItem | null>(null);

  const reload = useCallback(() => {
    setRefreshKey((value) => value + 1);
    onChanged?.();
  }, [onChanged]);

  const confirmDelete = async () => {
    if (!target) return;
    setBusy(true);
    setError(null);
    try {
      if (target.kind === "decision") {
        await deleteAdminDecisionItem(target.item.id, reason);
        setUndoItem({ kind: "decision", id: target.item.id, label: target.item.text });
      } else {
        await deleteAdminDecisionTask(target.item.id, reason);
        setUndoItem({ kind: "task", id: target.item.id, label: target.item.title });
      }
      setTarget(null);
      setReason("");
      reload();
    } catch (cause) {
      setError(describeActionError(cause));
    } finally {
      setBusy(false);
    }
  };

  const handleRestore = async () => {
    if (!undoItem) return;
    setBusy(true);
    setError(null);
    try {
      if (undoItem.kind === "decision") {
        await restoreAdminDecisionItem(undoItem.id);
      } else {
        await restoreAdminDecisionTask(undoItem.id);
      }
      setUndoItem(null);
      reload();
    } catch (cause) {
      setError(describeActionError(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem", minWidth: 0 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: ".5rem", flexWrap: "wrap" }}>
        <button type="button" onClick={onBack}>← Пульт</button>
        {onOpenNativeTaskQueue && (
          <button type="button" onClick={onOpenNativeTaskQueue}>Открыть в боте</button>
        )}
      </div>

      <div>
        <p style={{ margin: "0 0 .2rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
          Очередь решений
        </p>
        <h1 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>Пункты, требующие решения</h1>
        <p style={{ margin: ".35rem 0 0", color: "var(--era-text-muted)", fontSize: ".85rem", lineHeight: 1.45 }}>
          Неактуальные пункты и задания можно убрать с подтверждением — удаление записывается в журнал аудита и обратимо.
        </p>
      </div>

      {error && (
        <p role="alert" style={{ margin: 0, color: "var(--era-error)", fontSize: ".85rem" }}>
          {error}
        </p>
      )}

      {undoItem && (
        <Card style={{ background: "var(--era-surface-2)", display: "flex", justifyContent: "space-between", alignItems: "center", gap: ".75rem", flexWrap: "wrap" }}>
          <span role="status" style={{ fontSize: ".85rem", minWidth: 0, overflowWrap: "anywhere" }}>
            Убрано из очереди: <strong>{undoItem.label}</strong>
          </span>
          <button type="button" disabled={busy} onClick={handleRestore}>
            Вернуть
          </button>
        </Card>
      )}

      {queue.status === "loading" && <p style={{ color: "var(--era-text-muted)", margin: 0 }}>Загружаем очередь решений…</p>}
      {queue.status === "error" && (
        <EmptyState text="Не удалось загрузить очередь решений. Попробуйте обновить экран." />
      )}

      {queue.status === "ready" && queue.data.total === 0 && (
        <Card style={{ background: "var(--era-surface-2)", textAlign: "center", padding: "1.1rem" }}>
          <strong>Очередь решений чистая ✓</strong>
          <p style={{ margin: ".3rem 0 0", color: "var(--era-text-muted)", fontSize: ".84rem" }}>
            Нет задач и эскалаций, требующих решения администратора.
          </p>
        </Card>
      )}

      {queue.status === "ready" && queue.data.decisions.length > 0 && (
        <section aria-label="Пункты на решение" data-testid="decision-queue-items" style={{ display: "flex", flexDirection: "column", gap: ".6rem" }}>
          <h2 style={{ margin: 0, fontSize: "var(--era-text-lg)" }}>
            Сигналы и эскалации · {queue.data.decisions.length}
          </h2>
          {queue.data.decisions.map((item) => (
            <Card key={`decision-${item.id}`} style={{ display: "flex", flexDirection: "column", gap: ".55rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: ".5rem", flexWrap: "wrap" }}>
                <StatusBadge
                  label={DECISION_STATUS_LABELS[item.status] ?? item.status}
                  tone={item.severity === "high" ? "red" : "violet"}
                />
                <span style={{ color: "var(--era-text-muted)", fontSize: ".78rem" }}>{formatDate(item.created_at)}</span>
              </div>
              <p style={{ margin: 0, overflowWrap: "anywhere", lineHeight: 1.4 }}>{item.text}</p>
              {item.owner_name && (
                <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: ".8rem" }}>
                  Инициатор: {item.owner_name}
                </p>
              )}
              <div style={{ display: "flex", gap: ".5rem", flexWrap: "wrap" }}>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setError(null);
                    setReason("");
                    setTarget({ kind: "decision", item });
                  }}
                >
                  Удалить
                </button>
              </div>
            </Card>
          ))}
        </section>
      )}

      {queue.status === "ready" && queue.data.tasks.length > 0 && (
        <section aria-label="Задачи, требующие внимания" data-testid="decision-queue-tasks" style={{ display: "flex", flexDirection: "column", gap: ".6rem" }}>
          <h2 style={{ margin: 0, fontSize: "var(--era-text-lg)" }}>
            Задачи, требующие решения · {queue.data.tasks.length}
          </h2>
          {queue.data.tasks.map((task) => (
            <Card key={`task-${task.id}`} style={{ display: "flex", flexDirection: "column", gap: ".55rem" }}>
              <strong style={{ overflowWrap: "anywhere" }}>{task.title}</strong>
              <div style={{ display: "flex", gap: ".35rem", flexWrap: "wrap" }}>
                {task.reasons.map((code) => (
                  <StatusBadge
                    key={code}
                    label={TASK_REASON_LABELS[code] ?? code}
                    tone={code === "overdue" || code === "blocker" ? "red" : "violet"}
                  />
                ))}
              </div>
              <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: ".8rem" }}>
                {task.assignee_name ? `Исполнитель: ${task.assignee_name} · ` : ""}
                Срок: {formatDate(task.deadline)} · {task.points} баллов
              </p>
              <div style={{ display: "flex", gap: ".5rem", flexWrap: "wrap" }}>
                {task.pending_submissions_count > 0 ? (
                  <button type="button" className="era-btn-primary" onClick={onOpenTaskReview}>
                    Проверить ответ ({task.pending_submissions_count})
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={busy || !task.can_delete}
                    onClick={() => {
                      setError(null);
                      setReason("");
                      setTarget({ kind: "task", item: task });
                    }}
                  >
                    Удалить
                  </button>
                )}
              </div>
            </Card>
          ))}
        </section>
      )}

      <BottomSheet
        open={target !== null}
        title="Удалить из очереди решений?"
        onClose={() => {
          if (!busy) setTarget(null);
        }}
      >
        {target && (
          <div style={{ display: "flex", flexDirection: "column", gap: ".75rem" }}>
            <p style={{ margin: 0, fontWeight: 700, overflowWrap: "anywhere" }}>
              {target.kind === "decision" ? target.item.text : target.item.title}
            </p>
            <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: ".85rem", lineHeight: 1.45 }}>
              {target.kind === "decision"
                ? "Пункт будет убран из очереди решений. Запись сохранится в журнале аудита, и удаление можно будет отменить."
                : "Задача будет переведена в статус «Отменена» и убрана из очереди. Действие фиксируется в журнале аудита и обратимо."}
            </p>
            <label style={{ display: "flex", flexDirection: "column", gap: ".35rem", fontSize: ".85rem" }}>
              Причина (необязательно)
              <input
                type="text"
                maxLength={500}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Например: неактуально или дубль"
                style={{
                  minHeight: "2.6rem",
                  padding: ".55rem .75rem",
                  borderRadius: ".75rem",
                  border: "1px solid var(--era-border)",
                  background: "var(--era-surface)",
                  color: "var(--era-text)",
                }}
              />
            </label>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: ".5rem" }}>
              <button type="button" disabled={busy} onClick={() => setTarget(null)}>
                Отмена
              </button>
              <button type="button" className="era-btn-primary" disabled={busy} onClick={confirmDelete}>
                {busy ? "Удаляем…" : "Подтвердить удаление"}
              </button>
            </div>
          </div>
        )}
      </BottomSheet>
    </div>
  );
}
