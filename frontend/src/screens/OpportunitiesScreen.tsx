import { useCallback, useState } from "react";
import { applyToOpportunity, fetchOpportunities, saveOpportunity, unsaveOpportunity } from "../api/client";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { PillTabs } from "../components/PillTabs";
import { StatusBadge } from "../components/StatusBadge";
import { useAsync } from "../hooks/useAsync";
import type { OpportunityScope } from "../types/opportunity";

const SCOPES: { value: OpportunityScope; label: string }[] = [
  { value: "for_me", label: "Для тебя" },
  { value: "all", label: "Все" },
  { value: "saved", label: "Сохранённые" },
  { value: "mine", label: "Мои заявки" },
];

const APPLICATION_STATUS_LABELS: Record<string, string> = {
  pending: "на проверке",
  approved: "одобрена",
  rejected: "отклонена",
};

export function OpportunitiesScreen() {
  const [scope, setScope] = useState<OpportunityScope>("for_me");
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchOpportunities(scope), [scope, refreshKey]);
  const [pendingId, setPendingId] = useState<number | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleApply = useCallback(
    async (offerId: number) => {
      setPendingId(offerId);
      try {
        await applyToOpportunity(offerId);
        refresh();
      } finally {
        setPendingId(null);
      }
    },
    [refresh],
  );

  const handleToggleSave = useCallback(
    async (offerId: number, isSaved: boolean) => {
      setPendingId(offerId);
      try {
        if (isSaved) {
          await unsaveOpportunity(offerId);
        } else {
          await saveOpportunity(offerId);
        }
        refresh();
      } finally {
        setPendingId(null);
      }
    },
    [refresh],
  );

  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "1.375rem", margin: 0 }}>
        Возможности
      </h1>
      <PillTabs options={SCOPES} active={scope} onChange={setScope} />

      {state.status === "loading" && (
        <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>
      )}
      {state.status === "error" && <EmptyState text="Не удалось загрузить возможности." />}
      {state.status === "ready" && state.data.length === 0 && (
        <EmptyState text="В этом разделе пока пусто." />
      )}
      {state.status === "ready" &&
        state.data.map((offer) => {
          const applied = offer.application_status === "pending" || offer.application_status === "approved";
          return (
            <Card key={offer.id}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
                <strong>{offer.title}</strong>
                {offer.application_status && (
                  <StatusBadge
                    label={APPLICATION_STATUS_LABELS[offer.application_status] ?? offer.application_status}
                    tone="violet"
                  />
                )}
              </div>
              <p style={{ margin: "0.25rem 0", color: "var(--era-text-muted)" }}>{offer.partner_name}</p>
              {offer.reasons.length > 0 && (
                <p style={{ margin: "0 0 0.5rem", color: "var(--era-violet)", fontSize: "0.8125rem" }}>
                  Подходит вам: {offer.reasons.join(", ")}
                </p>
              )}
              <p style={{ margin: "0 0 0.5rem", color: "var(--era-text-muted)" }}>
                {offer.point_cost} баллов · мест: {offer.remaining_slots}
                {offer.expires_at ? ` · до ${offer.expires_at.slice(0, 10)}` : ""}
              </p>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                {!applied && (
                  <button
                    type="button"
                    className="era-btn-primary"
                    disabled={pendingId === offer.id}
                    onClick={() => handleApply(offer.id)}
                  >
                    Подать заявку
                  </button>
                )}
                <button
                  type="button"
                  disabled={pendingId === offer.id}
                  onClick={() => handleToggleSave(offer.id, offer.is_saved)}
                >
                  {offer.is_saved ? "Убрать из сохранённых" : "Сохранить"}
                </button>
              </div>
            </Card>
          );
        })}
    </div>
  );
}
