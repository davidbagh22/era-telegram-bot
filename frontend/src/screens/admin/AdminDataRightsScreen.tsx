import { useCallback, useState } from "react";
import { describeActionError, fetchDeletionRequests, fulfillDeletionRequest } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { useAsync } from "../../hooks/useAsync";

/** Review queue for self-service account-deletion requests — see
 * app/services/data_rights_service.py. Fulfilling with "approve" anonymizes
 * the target's PII and archives the account; it does not hard-delete the
 * row (see DataDeletionRequest's own docstring for why). Gated server-side
 * to full admins only (require_full_admin in app/api/v1/admin.py), unlike
 * the reversible block/archive actions in AdminUsersScreen. */
export function AdminDataRightsScreen() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchDeletionRequests(), [refreshKey]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleDecide = useCallback(
    async (requestId: number, approve: boolean) => {
      setBusyId(requestId);
      setActionError(null);
      try {
        await fulfillDeletionRequest(requestId, approve);
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [refresh],
  );

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }
  if (state.status === "error") {
    return <EmptyState text="Не удалось загрузить заявки на удаление аккаунта." />;
  }
  if (state.data.length === 0) {
    return <EmptyState text="Заявок на удаление аккаунта нет." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}
      {state.data.map((request) => (
        <Card key={request.id}>
          <strong>
            {request.first_name}
            {request.last_name ? ` ${request.last_name}` : ""}
          </strong>
          <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>
            Telegram ID {request.telegram_id}
            {request.note ? ` · «${request.note}»` : ""}
          </p>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              type="button"
              className="era-btn-primary"
              disabled={busyId === request.id}
              onClick={() => handleDecide(request.id, true)}
            >
              Подтвердить и обезличить
            </button>
            <button
              type="button"
              disabled={busyId === request.id}
              onClick={() => handleDecide(request.id, false)}
            >
              Отклонить
            </button>
          </div>
        </Card>
      ))}
    </div>
  );
}
