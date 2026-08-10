import { useCallback, useState } from "react";
import { decideActivitySubmission, describeActionError, fetchAdminActivitySubmissions } from "../../../api/client";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";

const STATUS_LABELS: Record<string, string> = {
  pending: "на проверке у админа",
  leader_approved: "проверено лидером",
};

// Final review — pending submissions plus anything a leader already
// pre-approved (see app/api/v1/leader.py's own activities endpoints for
// that earlier step). Spans every event, unlike EventActivitiesPanel.
export function ActivitySubmissionsPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAdminActivitySubmissions(), [refreshKey]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleDecide = useCallback(
    async (submissionId: number, action: "approve" | "reject") => {
      setBusyId(submissionId);
      setActionError(null);
      try {
        await decideActivitySubmission(submissionId, action);
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [refresh],
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}
      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить активности." />}
      {state.status === "ready" && state.data.length === 0 && (
        <EmptyState text="Активностей на проверке нет." />
      )}
      {state.status === "ready" &&
        state.data.map((submission) => (
          <Card key={submission.id}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
              <strong>{submission.activity_title}</strong>
              <StatusBadge label={STATUS_LABELS[submission.status] ?? submission.status} tone="violet" />
            </div>
            <p style={{ margin: "0.25rem 0", color: "var(--era-text-muted)" }}>
              {submission.event_title} · {submission.user_name}
            </p>
            <p style={{ margin: "0 0 0.5rem", fontSize: "0.875rem" }}>
              {submission.text || `материал прикреплён (${submission.file_type ?? "файл"})`}
            </p>
            <p style={{ margin: "0 0 0.5rem", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
              +{submission.points} баллов
            </p>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button
                type="button"
                className="era-btn-primary"
                disabled={busyId === submission.id}
                onClick={() => handleDecide(submission.id, "approve")}
              >
                ✅ Принять и начислить
              </button>
              <button
                type="button"
                disabled={busyId === submission.id}
                onClick={() => handleDecide(submission.id, "reject")}
              >
                ❌ Отклонить
              </button>
            </div>
          </Card>
        ))}
    </div>
  );
}
