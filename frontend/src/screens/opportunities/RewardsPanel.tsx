import { useCallback, useState } from "react";
import { describeActionError, fetchRewards, redeemReward } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { useAsync } from "../../hooks/useAsync";

const STATUS_LABELS: Record<string, string> = {
  pending: "заявка отправлена",
  answered: "есть ответ команды",
  exchanged: "обменяно",
  rejected: "отклонено",
};

// Points-shop catalog — the participant-facing half of the reward_*
// handlers in app/handlers/participant/growth.py. Distinct from
// Auctions: the cost is fixed up front, and every redemption goes
// through an admin reply before points are ever debited.
export function RewardsPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchRewards(), [refreshKey]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleRedeem = useCallback(
    async (rewardId: number) => {
      setBusyId(rewardId);
      setActionError(null);
      try {
        await redeemReward(rewardId);
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
    return <EmptyState text="Не удалось загрузить каталог." />;
  }
  if (state.data.length === 0) {
    return <EmptyState text="Каталог возможностей пока пуст." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}
      {state.data.map((reward) => (
        <Card key={reward.id}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
            <strong>{reward.name}</strong>
            {reward.my_status && (
              <StatusBadge label={STATUS_LABELS[reward.my_status] ?? reward.my_status} tone="violet" />
            )}
          </div>
          <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>{reward.description}</p>
          <p style={{ margin: "0 0 0.5rem", fontSize: "0.875rem" }}>
            {reward.point_cost} баллов
            {reward.quantity != null ? ` · доступно: ${reward.quantity}` : ""}
          </p>
          {!reward.my_status && (
            <button
              type="button"
              className="era-btn-primary"
              disabled={busyId === reward.id}
              onClick={() => handleRedeem(reward.id)}
            >
              Обменять {reward.point_cost} баллов
            </button>
          )}
        </Card>
      ))}
    </div>
  );
}
