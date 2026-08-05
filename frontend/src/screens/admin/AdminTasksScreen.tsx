import { useCallback, useState } from "react";
import { decideTaskSubmission, describeActionError, fetchAdminTaskSubmissions } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { useAsync } from "../../hooks/useAsync";
import type { TaskReviewAction } from "../../types/admin";

const DECISIONS: { action: TaskReviewAction; label: string; primary?: boolean }[] = [
  { action: "approve", label: "Одобрить и начислить баллы", primary: true },
  { action: "revision", label: "На доработку" },
  { action: "reject", label: "Отклонить" },
];

export function AdminTasksScreen() {
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

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }
  if (state.status === "error") {
    return <EmptyState text="Не удалось загрузить результаты заданий." />;
  }
  if (state.data.length === 0) {
    return <EmptyState text="Результатов заданий на проверке нет." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}
      {state.data.map((submission) => (
        <Card key={submission.id}>
          <strong>{submission.task_title}</strong>
          <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>
            {submission.participant_name} · {submission.points} баллов
          </p>
          {submission.text && (
            <p style={{ margin: "0 0 0.5rem" }}>{submission.text}</p>
          )}
          <textarea
            placeholder="Комментарий участнику (обязателен для доработки/отклонения)"
            value={comments[submission.id] ?? ""}
            onChange={(input) =>
              setComments((previous) => ({ ...previous, [submission.id]: input.target.value }))
            }
            rows={2}
            style={{
              width: "100%",
              fontFamily: "var(--era-font-body)",
              padding: "0.5rem",
              borderRadius: "0.5rem",
              border: "1px solid var(--era-border)",
              background: "var(--era-bg)",
              color: "var(--era-text)",
              marginBottom: "0.5rem",
            }}
          />
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            {DECISIONS.map(({ action, label, primary }) => (
              <button
                key={action}
                type="button"
                className={primary ? "era-btn-primary" : undefined}
                disabled={busyId === submission.id}
                onClick={() => handleDecide(submission.id, action)}
              >
                {label}
              </button>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}
