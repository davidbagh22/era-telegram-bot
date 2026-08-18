import { useCallback, useState } from "react";
import {
  decideTaskSubmission,
  describeActionError,
  fetchAdminTaskSubmissions,
  fetchMissionTemplates,
  launchAllMissions,
  launchMission,
} from "../../api/client";
import { ActionCell } from "../../components/ActionCell";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { useAsync } from "../../hooks/useAsync";
import { OpenTasksTab } from "../leader/OpenTasksTab";
import type { TaskReviewAction } from "../../types/admin";

const DECISIONS: { action: TaskReviewAction; label: string; primary?: boolean }[] = [
  { action: "approve", label: "Одобрить и начислить баллы", primary: true },
  { action: "revision", label: "На доработку" },
  { action: "reject", label: "Отклонить" },
];

type TasksSection = "review" | "create" | "missions";

export function AdminTasksScreen() {
  const [section, setSection] = useState<TasksSection | null>(null);

  if (!section) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <Card gradient>
          <p style={{ margin: "0 0 0.25rem", color: "var(--era-text-secondary)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Задания</p>
          <h2 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>Дать работу или проверить результат</h2>
          <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-secondary)" }}>Создание и проверка разделены явно, чтобы администратор сразу понимал следующий шаг.</p>
        </Card>
        <ActionCell title="Создать задание" description="Открыть задачу, назначить аудиторию, срок и баллы" leading="＋" onClick={() => setSection("create")} />
        <ActionCell title="Проверить результаты" description="Принять работу, отправить на доработку или отклонить" leading="✓" onClick={() => setSection("review")} />
        <ActionCell title="Community Missions" description="Запустить 26 авторских заданий как реальные задачи" leading="◎" onClick={() => setSection("missions")} />
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" onClick={() => setSection(null)} style={{ alignSelf: "flex-start" }}>← К заданиям</button>
      <h2 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>{section === "create" ? "Создать задание" : section === "review" ? "Проверить результаты" : "Community Missions"}</h2>
      {section === "create" && <OpenTasksTab />}
      {section === "review" && <TaskSubmissionReview />}
      {section === "missions" && <MissionTemplatesPanel />}
    </div>
  );
}

/** DELTA ToR §13/§76 Phase 2 item 9: the 26 authored missions are seeded
 * idempotently every boot but never became real, visible Tasks -- this is
 * the missing human trigger, reusing the already-built launch endpoints. */
function MissionTemplatesPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchMissionTemplates(), [refreshKey]);
  const [busyId, setBusyId] = useState<number | "all" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const launchOne = async (templateId: number) => {
    setBusyId(templateId);
    setError(null);
    try {
      await launchMission(templateId);
      setStatus("Задача создана.");
      refresh();
    } catch (cause) {
      setError(describeActionError(cause));
    } finally {
      setBusyId(null);
    }
  };

  const launchAll = async () => {
    setBusyId("all");
    setError(null);
    try {
      const launched = await launchAllMissions();
      setStatus(launched.length ? `Запущено заданий: ${launched.length}.` : "Все миссии уже запущены.");
      refresh();
    } catch (cause) {
      setError(describeActionError(cause));
    } finally {
      setBusyId(null);
    }
  };

  if (state.status === "loading") return <EmptyState text="Загружаем шаблоны…" />;
  if (state.status === "error") return <EmptyState text="Не удалось загрузить шаблоны миссий." />;

  const pending = state.data.filter((template) => !template.is_launched).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <Card>
        <strong>{pending} из {state.data.length} ещё не запущены</strong>
        <p style={{ margin: "0.4rem 0 0", color: "var(--era-text-muted)", fontSize: "0.85rem" }}>Повторный запуск не создаёт дубликаты — уже запущенные миссии пропускаются.</p>
        <button type="button" disabled={busyId === "all" || pending === 0} onClick={() => void launchAll()} style={{ marginTop: "0.6rem" }}>
          {busyId === "all" ? "Запускаем…" : "Запустить все не запущенные"}
        </button>
      </Card>
      {status && <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.85rem" }}>{status}</p>}
      {error && <p style={{ margin: 0, color: "var(--era-error)", fontSize: "0.85rem" }}>{error}</p>}
      {state.data.map((template) => (
        <Card key={template.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem" }}>
          <div style={{ minWidth: 0 }}>
            <strong>{template.title}</strong>
            <div style={{ color: "var(--era-text-muted)", fontSize: "0.8rem", marginTop: 3 }}>
              {template.code} · месяц {template.month} · {template.claim_mode === "SOLO" ? "соло" : `команда ${template.min_people}-${template.max_people}`} · +{template.points}
            </div>
          </div>
          {template.is_launched ? (
            <span style={{ flexShrink: 0, color: "var(--era-text-muted)", fontSize: "0.8rem", fontWeight: 700 }}>Запущена</span>
          ) : (
            <button type="button" disabled={busyId === template.id} onClick={() => void launchOne(template.id)} style={{ flexShrink: 0 }}>
              {busyId === template.id ? "…" : "Запустить"}
            </button>
          )}
        </Card>
      ))}
    </div>
  );
}

function TaskSubmissionReview() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAdminTaskSubmissions(), [refreshKey]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [comments, setComments] = useState<Record<number, string>>({});
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleDecide = useCallback(
    async (submissionId: number, action: TaskReviewAction) => {
      const comment = (comments[submissionId] ?? "").trim();
      if (action !== "approve" && !comment) return;
      setBusyId(submissionId);
      setActionError(null);
      try {
        await decideTaskSubmission(submissionId, action, comment);
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [comments, refresh],
  );

  if (state.status === "loading") return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  if (state.status === "error") return <EmptyState text="Не удалось загрузить результаты заданий." />;
  if (state.data.length === 0) return <EmptyState text="Результатов заданий на проверке нет." />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {actionError && <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>}
      {state.data.map((submission) => (
        <Card key={submission.id}>
          <strong>{submission.task_title}</strong>
          <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>{submission.participant_name} · {submission.points} баллов</p>
          {submission.text && <p style={{ margin: "0 0 0.5rem" }}>{submission.text}</p>}
          <textarea
            placeholder="Комментарий участнику (обязателен для доработки/отклонения)"
            value={comments[submission.id] ?? ""}
            onChange={(input) => setComments((previous) => ({ ...previous, [submission.id]: input.target.value }))}
            rows={2}
            style={{ marginBottom: "0.5rem" }}
          />
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            {DECISIONS.map(({ action, label, primary }) => (
              <button key={action} type="button" className={primary ? "era-btn-primary" : undefined} disabled={busyId === submission.id} onClick={() => handleDecide(submission.id, action)}>
                {label}
              </button>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}
