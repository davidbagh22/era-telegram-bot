import { useCallback, useState } from "react";
import {
  answerRedemption,
  createReward,
  describeActionError,
  disableReward,
  exchangeRedemption,
  fetchAdminRedemptions,
  fetchAdminRewards,
  rejectRedemption,
} from "../../../api/client";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";

const inputStyle = {
  width: "100%",
  fontFamily: "var(--era-font-body)",
  padding: "0.5rem",
  borderRadius: "0.5rem",
  border: "1px solid var(--era-border)",
  background: "var(--era-bg)",
  color: "var(--era-text)",
} as const;

const REDEMPTION_STATUS_LABELS: Record<string, string> = {
  pending: "ожидает ответа",
  answered: "ответ отправлен",
};

// "Каталог возможностей" — the Mini App equivalent of the admin:reward*/
// admin:redemption* handlers in app/handlers/admin/panel.py. A reward's
// cost is fixed up front (unlike Auctions, where it's decided by
// bidding), and every redemption goes through an admin reply before
// points are ever debited.
export function RewardsPanel() {
  const [rewardsKey, setRewardsKey] = useState(0);
  const [redemptionsKey, setRedemptionsKey] = useState(0);
  const rewardsState = useAsync(() => fetchAdminRewards(), [rewardsKey]);
  const redemptionsState = useAsync(() => fetchAdminRedemptions(), [redemptionsKey]);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [pointCost, setPointCost] = useState("");
  const [quantity, setQuantity] = useState("");
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [answerDrafts, setAnswerDrafts] = useState<Record<number, string>>({});
  const [actionError, setActionError] = useState<string | null>(null);

  const refreshRewards = useCallback(() => setRewardsKey((key) => key + 1), []);
  const refreshRedemptions = useCallback(() => setRedemptionsKey((key) => key + 1), []);

  const canCreate = name.trim() && description.trim() && pointCost.trim();

  const handleCreate = useCallback(async () => {
    if (!canCreate) return;
    setCreating(true);
    setActionError(null);
    try {
      await createReward({
        name: name.trim(),
        description: description.trim(),
        point_cost: Number(pointCost),
        quantity: quantity.trim() ? Number(quantity) : null,
      });
      setName("");
      setDescription("");
      setPointCost("");
      setQuantity("");
      refreshRewards();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setCreating(false);
    }
  }, [canCreate, name, description, pointCost, quantity, refreshRewards]);

  const handleDisable = useCallback(
    async (rewardId: number) => {
      setBusyId(rewardId);
      setActionError(null);
      try {
        await disableReward(rewardId);
        refreshRewards();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [refreshRewards],
  );

  const runRedemptionAction = useCallback(
    async (redemptionId: number, action: () => Promise<unknown>) => {
      setBusyId(redemptionId);
      setActionError(null);
      try {
        await action();
        refreshRedemptions();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [refreshRedemptions],
  );

  const handleAnswer = useCallback(
    (redemptionId: number) => {
      const answer = (answerDrafts[redemptionId] ?? "").trim();
      if (!answer) return;
      return runRedemptionAction(redemptionId, () => answerRedemption(redemptionId, answer));
    },
    [answerDrafts, runRedemptionAction],
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}

      <Card>
        <strong>Новая возможность</strong>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
          <input placeholder="Название" value={name} onChange={(e) => setName(e.target.value)} style={inputStyle} />
          <textarea
            placeholder="Что получит участник"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            style={inputStyle}
          />
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <input
              type="number"
              placeholder="Стоимость в баллах"
              value={pointCost}
              onChange={(e) => setPointCost(e.target.value)}
              style={inputStyle}
            />
            <input
              type="number"
              placeholder="Количество (пусто — без ограничения)"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              style={inputStyle}
            />
          </div>
          <button type="button" className="era-btn-primary" disabled={creating || !canCreate} onClick={handleCreate}>
            Опубликовать в каталоге
          </button>
        </div>
      </Card>

      <strong>Каталог</strong>
      {rewardsState.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {rewardsState.status === "error" && <EmptyState text="Не удалось загрузить каталог." />}
      {rewardsState.status === "ready" && rewardsState.data.length === 0 && (
        <EmptyState text="Каталог пока пуст." />
      )}
      {rewardsState.status === "ready" &&
        rewardsState.data.map((reward) => (
          <Card key={reward.id}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
              <strong>{reward.name}</strong>
              <StatusBadge label={reward.is_active ? "активна" : "скрыта"} tone="violet" />
            </div>
            <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>{reward.description}</p>
            <p style={{ margin: "0 0 0.5rem", fontSize: "0.875rem" }}>
              {reward.point_cost} баллов
              {reward.quantity != null ? ` · доступно: ${reward.quantity}` : ""}
            </p>
            {reward.is_active && (
              <button type="button" disabled={busyId === reward.id} onClick={() => handleDisable(reward.id)}>
                Скрыть из каталога
              </button>
            )}
          </Card>
        ))}

      <strong>Заявки на обмен</strong>
      {redemptionsState.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {redemptionsState.status === "error" && <EmptyState text="Не удалось загрузить заявки." />}
      {redemptionsState.status === "ready" && redemptionsState.data.length === 0 && (
        <EmptyState text="Новых заявок нет." />
      )}
      {redemptionsState.status === "ready" &&
        redemptionsState.data.map((redemption) => (
          <Card key={redemption.id}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
              <strong>{redemption.reward_name}</strong>
              <StatusBadge
                label={REDEMPTION_STATUS_LABELS[redemption.status] ?? redemption.status}
                tone="violet"
              />
            </div>
            <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>
              {redemption.user_name} · {redemption.points_spent} баллов
            </p>
            {redemption.admin_comment && (
              <p style={{ margin: "0 0 0.5rem", fontSize: "0.875rem" }}>Ответ: {redemption.admin_comment}</p>
            )}
            {redemption.status === "pending" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <textarea
                  placeholder="Ответ участнику"
                  value={answerDrafts[redemption.id] ?? ""}
                  onChange={(e) =>
                    setAnswerDrafts((previous) => ({ ...previous, [redemption.id]: e.target.value }))
                  }
                  rows={2}
                  style={inputStyle}
                />
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button
                    type="button"
                    className="era-btn-primary"
                    disabled={busyId === redemption.id || !(answerDrafts[redemption.id] ?? "").trim()}
                    onClick={() => handleAnswer(redemption.id)}
                  >
                    Отправить ответ
                  </button>
                  <button
                    type="button"
                    disabled={busyId === redemption.id}
                    onClick={() => runRedemptionAction(redemption.id, () => rejectRedemption(redemption.id))}
                  >
                    Отклонить без списания
                  </button>
                </div>
              </div>
            )}
            {redemption.status === "answered" && (
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button
                  type="button"
                  className="era-btn-primary"
                  disabled={busyId === redemption.id}
                  onClick={() => runRedemptionAction(redemption.id, () => exchangeRedemption(redemption.id))}
                >
                  Обменять и списать баллы
                </button>
                <button
                  type="button"
                  disabled={busyId === redemption.id}
                  onClick={() => runRedemptionAction(redemption.id, () => rejectRedemption(redemption.id))}
                >
                  Отклонить без списания
                </button>
              </div>
            )}
          </Card>
        ))}
    </div>
  );
}
