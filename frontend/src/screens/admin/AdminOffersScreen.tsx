import { useCallback, useState } from "react";
import {
  decideOfferApplication,
  describeActionError,
  fetchAdminOfferApplications,
} from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { useAsync } from "../../hooks/useAsync";
import type { OfferApplicationAction } from "../../types/admin";

export function AdminOffersScreen() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAdminOfferApplications(), [refreshKey]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleDecide = useCallback(
    async (applicationId: number, action: OfferApplicationAction) => {
      setBusyId(applicationId);
      setActionError(null);
      try {
        await decideOfferApplication(applicationId, action);
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
    return <EmptyState text="Не удалось загрузить заявки на возможности." />;
  }
  if (state.data.length === 0) {
    return <EmptyState text="Заявок на возможности нет." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}
      {state.data.map((application) => (
        <Card key={application.id}>
          <strong>{application.offer_title}</strong>
          <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>
            {application.participant_name} · стоимость {application.point_cost} баллов · баланс{" "}
            {application.participant_balance}
          </p>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              type="button"
              className="era-btn-primary"
              disabled={busyId === application.id}
              onClick={() => handleDecide(application.id, "approve")}
            >
              Одобрить и списать баллы
            </button>
            <button
              type="button"
              disabled={busyId === application.id}
              onClick={() => handleDecide(application.id, "reject")}
            >
              Отклонить
            </button>
          </div>
        </Card>
      ))}
    </div>
  );
}
