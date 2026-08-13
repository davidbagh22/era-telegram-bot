import { useCallback, useState } from "react";
import {
  approveApplication,
  describeActionError,
  fetchAdminApplications,
  rejectApplication,
  requestApplicationInfo,
} from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { InitialsAvatar } from "../../components/InitialsAvatar";
import { useAsync } from "../../hooks/useAsync";

export function AdminApplicationsScreen() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAdminApplications(), [refreshKey]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [comments, setComments] = useState<Record<number, string>>({});
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleApprove = useCallback(
    async (userId: number) => {
      setBusyId(userId);
      setActionError(null);
      try {
        await approveApplication(userId);
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [refresh],
  );

  const handleReject = useCallback(
    async (userId: number) => {
      const comment = (comments[userId] ?? "").trim();
      if (!comment) return;
      setBusyId(userId);
      setActionError(null);
      try {
        await rejectApplication(userId, comment);
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [comments, refresh],
  );

  const handleRequestInfo = useCallback(
    async (userId: number) => {
      const comment = (comments[userId] ?? "").trim();
      if (!comment) return;
      setBusyId(userId);
      setActionError(null);
      try {
        await requestApplicationInfo(userId, comment);
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
    return <EmptyState text="Не удалось загрузить заявки." />;
  }
  if (state.data.length === 0) {
    return <EmptyState text="Новых заявок нет." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}
      {state.data.map((application) => (
        <Card key={application.id} style={{ borderLeft: "3px solid var(--era-gold)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "0.25rem" }}>
            <InitialsAvatar firstName={application.first_name} lastName={application.last_name} />
            <strong>
              {application.first_name} {application.last_name ?? ""}
            </strong>
          </div>
          <p style={{ margin: "0.25rem 0", color: "var(--era-text-muted)" }}>
            {application.city ?? "—"} · {application.occupation ?? "—"}
          </p>
          {application.motivation && (
            <p style={{ margin: "0 0 0.5rem" }}>{application.motivation}</p>
          )}
          <textarea
            placeholder="Комментарий (для отклонения или запроса информации)"
            value={comments[application.id] ?? ""}
            onChange={(event) =>
              setComments((previous) => ({ ...previous, [application.id]: event.target.value }))
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
            <button
              type="button"
              className="era-btn-primary"
              disabled={busyId === application.id}
              onClick={() => handleApprove(application.id)}
            >
              Одобрить
            </button>
            <button
              type="button"
              disabled={busyId === application.id}
              onClick={() => handleRequestInfo(application.id)}
            >
              Запросить информацию
            </button>
            <button
              type="button"
              disabled={busyId === application.id}
              onClick={() => handleReject(application.id)}
            >
              Отклонить
            </button>
          </div>
        </Card>
      ))}
    </div>
  );
}
