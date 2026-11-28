import { useCallback, useEffect, useState } from "react";
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
import { TaskSquadPanel } from "./TaskSquadPanel";

const PAGE_SIZE = 8;

const CLAIM_MODE_LABELS: Record<string, string> = {
  SOLO: "Соло",
  TEAM: "Команда",
  SOLO_OR_TEAM: "Соло или команда",
};

// DELTA ToR §8: the full 6-scope model, shown through the existing
// single-selector BottomSheet pattern rather than 6 horizontal tabs.
const SCOPES: { value: TaskScope; label: string; description: string }[] = [
  { value: "for_you", label: "Для тебя", description: "Подобрано по направлению и дедлайну" },
  { value: "available", label: "Доступные", description: "Задачи, к которым можно присоединиться" },
  { value: "mine", label: "Мои", description: "То, что уже взято в работу" },
  { value: "team", label: "Командные", description: "Задачи с несколькими участниками" },
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

function pluralRu(count: number, one: string, few: string, many: string): string {
  const n = Math.abs(count) % 100;
  if (n >= 11 && n <= 19) return many;
  const last = n % 10;
  if (last === 1) return one;
  if (last >= 2 && last <= 4) return few;
  return many;
}

function scopeSummaryLabel(scope: TaskScope, count: number): string {
  if (scope === "mine") {
    return `${count} ${pluralRu(count, "задача в работе", "задачи в работе", "задач в работе")}`;
  }
  if (scope === "review") {
    return `${count} ${pluralRu(count, "задача на проверке", "задачи на проверке", "задач на проверке")}`;
  }
  if (scope === "completed") {
    return `${count} ${pluralRu(count, "выполненная задача", "выполненные задачи", "выполненных задач")}`;
  }
  return `${count} ${pluralRu(count, "открытая задача", "открытые задачи", "открытых задач")}`;
}

function statusTone(status: string): "neutral" | "violet" | "red" | "gold" | "success" {
  if (status === "overdue" || status === "cancelled") return "red";
  if (status === "completed") return "success";
  if (status === "review") return "gold";
  return "violet";
}

function formatTaskDeadline(raw: string | null | undefined, withTime = false): string {
  if (!raw) return "Без срока";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return "Без срока";
  return parsed.toLocaleString(
    "ru-RU",
    withTime
      ? { timeZone: "Asia/Yerevan", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" }
      : { timeZone: "Asia/Yerevan", day: "2-digit", month: "2-digit", year: "numeric" },
  );
}

function formatGroupHeading(task: TaskItem): string {
  if (task.group_kind === "event") {
    return task.group_date
      ? `📅 ${task.group_title ?? "Событие"} · ${task.group_date}`
      : `📅 ${task.group_title ?? "Событие"}`;
  }
  if (task.group_kind === "project") {
    return task.group_date
      ? `💡 ${task.group_title ?? "Проект"} · ${task.group_date}`
      : `💡 ${task.group_title ?? "Проект"}`;
  }
  if (task.group_kind === "media") {
    return task.group_date
      ? `🎬 ${task.group_title ?? "Медиа"} · ${task.group_date}`
      : `🎬 ${task.group_title ?? "Медиа"}`;
  }
  return "📌 Общие задачи";
}

interface TaskGroupBucket {
  key: string;
  heading: string | null;
  isNamed: boolean;
  tasks: TaskItem[];
}

function groupPageTasks(tasks: TaskItem[]): TaskGroupBucket[] {
  const hasNamedGroups = tasks.some(
    (task) => task.group_kind && task.group_kind !== "general" && Boolean(task.group_title),
  );
  if (!hasNamedGroups) {
    return [{ key: "flat", heading: null, isNamed: false, tasks }];
  }
  const buckets: TaskGroupBucket[] = [];
  for (const task of tasks) {
    const key = task.group_key || "general";
    const isNamed = Boolean(task.group_kind && task.group_kind !== "general" && task.group_title);
    const prev = buckets[buckets.length - 1];
    if (prev && prev.key === key) {
      prev.tasks.push(task);
    } else {
      buckets.push({
        key,
        heading: formatGroupHeading(task),
        isNamed,
        tasks: [task],
      });
    }
  }
  return buckets;
}

/**
 * Strip pack meta preamble; keep a short human description for list cards.
 * Pack lines look like: "Тип: Media Команда: 1–4 Чат: media <instruction>"
 * — meta and instruction share one line, so never wipe a whole line as meta.
 */
export function taskListDescription(raw: string, limit = 140): string {
  const original = (raw || "").trim();
  if (!original) return "";
  let text = original;
  const taskMark = /(?:^|\n)Задача:\s*/i.exec(text);
  if (taskMark) {
    text = text.slice(taskMark.index + taskMark[0].length).trim();
  }
  // Fixed field order from community missions pack. Deadline values are short
  // ("14 дней"); stop before the first real instruction sentence.
  const packMeta = text.match(
    /^Тип:\s*.+?\s+Команда:\s*.+?\s+Чат:\s*\S+(?:\s+Дедлайн:\s*\d+\s*(?:дн(?:я|ей|ень)|недел[ьяи]|час(?:а|ов)?)?)?\s*/iu,
  );
  if (packMeta) {
    text = text.slice(packMeta[0].length).trim();
  } else {
    // Drop leading meta tokens only when the next known key follows.
    text = text
      .replace(/^Тип:\s*.+?(?=\s+Команда:)/iu, "")
      .replace(/^\s*Команда:\s*.+?(?=\s+Чат:)/iu, "")
      .replace(/^\s*Чат:\s*\S+(?=\s+(?:Дедлайн:|[«"A-ZА-ЯЁ]))/iu, "")
      .replace(/^\s*Дедлайн:\s*\d+\s*(?:дн(?:я|ей|ень)|недел[ьяи]|час(?:а|ов)?)?/iu, "")
      .trim();
  }
  text = text.replace(/\s+/g, " ").trim();
  if (!text) {
    // Boundary unclear — keep a truncated original rather than an empty card.
    text = original.replace(/\s+/g, " ").trim();
  }
  if (text.length <= limit) return text;
  return `${text.slice(0, limit - 1).trimEnd()}…`;
}

interface TasksTabProps {
  initialItemId?: number | null;
}

function TaskDetail({ task, onClaim, pending, error }: { task: TaskItem; onClaim: () => void; pending: boolean; error: string | null }) {
  const hasContext = Boolean(task.group_kind && task.group_kind !== "general" && task.group_title);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: ".75rem", paddingBottom: "1rem" }}>
      <button type="button" onClick={() => { window.location.hash = "#/tasks"; }} style={{ alignSelf: "flex-start" }}>← К заданиям</button>
      <EditorialHero eyebrow="Задание ЭРА" title={task.title} glow="hot">
        <div style={{ display: "flex", gap: ".45rem", flexWrap: "wrap" }}>
          <StatusBadge label={STATUS_LABELS[task.status] ?? "Статус обновлён"} tone={statusTone(task.status)} />
          <span style={{ padding: ".3rem .55rem", borderRadius: 999, background: "var(--era-tint-gold)", color: "var(--era-gold-ink)", fontSize: ".78rem", fontWeight: 850 }}>+{task.points} баллов</span>
          {task.claim_mode && (
            <span style={{ padding: ".3rem .55rem", borderRadius: 999, background: "var(--era-tint-violet)", color: "var(--era-violet)", fontSize: ".78rem", fontWeight: 850 }}>
              {CLAIM_MODE_LABELS[task.claim_mode] ?? task.claim_mode}
              {task.claim_mode !== "SOLO" && task.min_people ? ` ${task.min_people}–${task.max_people ?? task.min_people}` : ""}
            </span>
          )}
        </div>
      </EditorialHero>
      {hasContext && (
        <Card style={{ padding: ".85rem" }}>
          <span style={{ color: "var(--era-text-muted)", fontSize: ".76rem" }}>
            {task.group_kind === "event" ? "СОБЫТИЕ" : task.group_kind === "project" ? "ПРОЕКТ" : "МЕДИА"}
          </span>
          <strong style={{ display: "block", marginTop: 3, overflowWrap: "anywhere" }}>
            {task.group_title}{task.group_date ? ` · ${task.group_date}` : ""}
          </strong>
        </Card>
      )}
      <Card>
        <strong>Что нужно сделать</strong>
        <p style={{ margin: ".45rem 0 0", whiteSpace: "pre-wrap", lineHeight: 1.55, color: "var(--era-text-muted)" }}>{task.description}</p>
      </Card>
      <Card style={{ padding: ".85rem" }}>
        <span style={{ color: "var(--era-text-muted)", fontSize: ".76rem" }}>СРОК</span>
        <strong style={{ display: "block", marginTop: 3 }}>{formatTaskDeadline(task.deadline, true)}</strong>
      </Card>
      {task.deliverable && (
        <Card style={{ padding: ".85rem" }}>
          <span style={{ color: "var(--era-text-muted)", fontSize: ".76rem" }}>РЕЗУЛЬТАТ</span>
          <strong style={{ display: "block", marginTop: 3 }}>{task.deliverable}</strong>
        </Card>
      )}
      {error && <p style={{ margin: 0, color: "var(--era-error)" }}>{error}</p>}
      {!task.is_joined_or_assigned && ["new", "published"].includes(task.status) && (
        <button type="button" className="era-btn-primary" disabled={pending} onClick={onClaim}>
          {pending
            ? "Сохраняем…"
            : !task.claim_mode
              ? "Хочу помочь"
              : task.claim_mode === "SOLO"
                ? "Взять задачу"
                : "Присоединиться к команде"}
        </button>
      )}
      {task.can_submit && task.submit_deep_link && <a href={task.submit_deep_link} target="_blank" rel="noreferrer" className="era-btn-primary" style={{ textAlign: "center", textDecoration: "none" }}>Отправить результат в боте</a>}
      {task.claim_mode && task.claim_mode !== "SOLO" && <TaskSquadPanel task={task} />}
    </div>
  );
}

export function TasksTab({ initialItemId }: TasksTabProps = {}) {
  // ToR §8: "Для тебя" is the landing scope on the first screen.
  const [scope, setScope] = useState<TaskScope>("for_you");
  const [page, setPage] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchTasks(scope), [scope, refreshKey]);
  const detail = useAsync(
    () => initialItemId ? fetchTaskDetail(initialItemId) : Promise.resolve(null),
    [initialItemId, refreshKey],
  );
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [filterOpen, setFilterOpen] = useState(false);

  useEffect(() => {
    setPage(0);
  }, [scope]);

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

  const scopeMeta = SCOPES.find((item) => item.value === scope) ?? SCOPES[0];
  const allTasks = state.status === "ready" ? state.data : [];
  const totalPages = Math.max(1, Math.ceil(allTasks.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const pageTasks = allTasks.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);
  const grouped = groupPageTasks(pageTasks);
  const isOpenScope = scope === "available" || scope === "for_you" || scope === "team";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" onClick={() => setFilterOpen(true)} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>Показать: <strong>{scopeMeta.label}</strong></span><span>⌄</span>
      </button>

      {state.status === "ready" && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: ".5rem", flexWrap: "wrap", fontSize: "0.84rem", color: "var(--era-text-muted)", padding: "0 0.15rem" }}>
          <strong>{scopeSummaryLabel(scope, allTasks.length)}</strong>
          {totalPages > 1 && <span>Стр. {safePage + 1} из {totalPages}</span>}
        </div>
      )}

      {actionError && <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>}
      {state.status === "loading" && <SkeletonList count={3} />}
      {state.status === "error" && <EmptyState text="Не удалось загрузить задачи." />}
      {state.status === "ready" && allTasks.length === 0 && (
        <EmptyState
          text={
            isOpenScope
              ? "Сейчас нет открытых задач. Как только команда опубликует набор, он появится здесь."
              : "Пока нет задач в этом разделе. Как только появится новое действие, оно будет здесь."
          }
        />
      )}
      {state.status === "ready" && grouped.map((bucket) => (
        <div key={bucket.key} style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
          {bucket.heading && (
            <div style={{ fontSize: "0.86rem", fontWeight: 700, color: "var(--era-text-muted)", padding: "0.2rem 0.15rem 0", overflowWrap: "anywhere" }}>
              {bucket.heading}
            </div>
          )}
          {bucket.tasks.map((task) => {
            const canTake = !task.is_joined_or_assigned && ["new", "published"].includes(task.status);
            const description = taskListDescription(task.description || task.deliverable || "");
            const cardTitle = bucket.isNamed && task.short_title ? task.short_title : task.title;
            const deadlineText = task.deadline ? `до ${formatTaskDeadline(task.deadline)}` : "Без срока";
            const showStatusBadge = !isOpenScope || task.status === "overdue";
            return (
              <Card key={task.id} style={{ padding: "0.85rem 0.9rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: ".55rem", alignItems: "flex-start" }}>
                  <strong style={{ fontSize: "1.02rem", lineHeight: 1.25, overflowWrap: "anywhere" }}>{cardTitle}</strong>
                  <span style={{ whiteSpace: "nowrap", color: "var(--era-gold-ink)", fontWeight: 800, fontSize: "0.86rem" }}>+{task.points}</span>
                </div>
                <div style={{ display: "flex", gap: "0.45rem", alignItems: "center", flexWrap: "wrap", marginTop: "0.35rem", fontSize: "0.78rem", color: "var(--era-text-muted)" }}>
                  <span>{deadlineText}</span>
                  {showStatusBadge && (
                    <StatusBadge
                      label={STATUS_LABELS[task.status] ?? task.status}
                      tone={statusTone(task.status)}
                    />
                  )}
                </div>
                {description ? (
                  <p style={{ margin: "0.45rem 0 0", color: "var(--era-text-muted)", fontSize: "0.86rem", lineHeight: 1.45, overflowWrap: "anywhere" }}>
                    {description}
                  </p>
                ) : null}
                <div style={{ display: "flex", gap: "0.45rem", marginTop: "0.7rem", flexWrap: "wrap" }}>
                  {canTake ? (
                    <button
                      type="button"
                      className="era-btn-primary"
                      disabled={pendingId !== null}
                      onClick={() => void handleClaim(task.id)}
                      style={{ flex: "1 1 8rem" }}
                    >
                      {pendingId === task.id ? "Сохраняем…" : "Взять"}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => { window.location.hash = `#/tasks/${task.id}`; }}
                    style={{ flex: "1 1 8rem" }}
                  >
                    {task.is_joined_or_assigned ? "К заданию" : "Подробнее"}
                  </button>
                </div>
              </Card>
            );
          })}
        </div>
      ))}

      {state.status === "ready" && totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem", paddingTop: "0.25rem" }}>
          <button
            type="button"
            disabled={safePage === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            style={{ flex: "1 1 6rem" }}
          >
            ← Назад
          </button>
          <span style={{ fontSize: "0.84rem", color: "var(--era-text-muted)", whiteSpace: "nowrap" }}>
            {safePage + 1} / {totalPages}
          </span>
          <button
            type="button"
            disabled={safePage + 1 >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            style={{ flex: "1 1 6rem" }}
          >
            Вперёд →
          </button>
        </div>
      )}

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