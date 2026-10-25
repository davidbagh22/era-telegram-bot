import { useCallback, useState } from "react";
import { decideLeaderActivity, describeActionError, fetchLeaderActivities } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { useAsync } from "../../hooks/useAsync";

// The Mini App equivalent of the leader pre-review step in
// app/handlers/leader/event_activities_block7.py — a submission passes
// through here before an admin can do the final points award, and a
// leader only ever sees submissions for events they're responsible for.
export function ActivitiesTab() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchLeaderActivities(), [refreshKey]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleDecide = useCallback(
    async (submissionId: number, action: "approve" | "reject") => {
      setBusyId(submissionId);
      setActionError(null);
      try {
        await decideLeaderActivity(submissionId, action);
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
            <strong>{submission.activity_title}</strong>
            <p style={{ margin: "0.25rem 0", color: "var(--era-text-muted)" }}>
              {submission.event_title} · {submission.user_name}
            </p>
            <p style={{ margin: "0 0 0.5rem", fontSize: "0.875rem" }}>
              {submission.text || `материал прикреплён (${submission.file_type ?? "файл"})`}
            </p>
            <p style={{ margin: "0 0 0.5rem", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
              +{submission.points} баллов после финального подтверждения админом
            </p>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button
                type="button"
                className="era-btn-primary"
                disabled={busyId === submission.id}
                onClick={() => handleDecide(submission.id, "approve")}
              >
                ✅ Принять
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
