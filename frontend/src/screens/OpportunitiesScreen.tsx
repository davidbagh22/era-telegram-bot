import { useCallback, useState } from "react";
import {
  applyToOpportunity,
  describeActionError,
  fetchOpportunities,
  saveOpportunity,
  unsaveOpportunity,
} from "../api/client";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { PillTabs } from "../components/PillTabs";
import { StatusBadge } from "../components/StatusBadge";
import { useAsync } from "../hooks/useAsync";
import { AuctionsPanel } from "./opportunities/AuctionsPanel";
import { RewardsPanel } from "./opportunities/RewardsPanel";
import { SurveysPanel } from "./opportunities/SurveysPanel";
import type { OpportunityScope } from "../types/opportunity";

type OpportunitiesTab = OpportunityScope | "auctions" | "surveys" | "rewards";

const NON_LIST_TABS: OpportunitiesTab[] = ["auctions", "surveys", "rewards"];

const SCOPES: { value: OpportunitiesTab; label: string }[] = [
  { value: "for_me", label: "Для тебя" },
  { value: "all", label: "Все" },
  { value: "saved", label: "Сохранённые" },
  { value: "mine", label: "Мои заявки" },
  { value: "auctions", label: "Аукционы" },
  { value: "rewards", label: "Каталог" },
  { value: "surveys", label: "Опросы" },
];

const APPLICATION_STATUS_LABELS: Record<string, string> = {
  pending: "на проверке",
  approved: "одобрена",
  rejected: "отклонена",
};

export function OpportunitiesScreen() {
  const [scope, setScope] = useState<OpportunitiesTab>("for_me");
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(
    () => (NON_LIST_TABS.includes(scope) ? Promise.resolve([]) : fetchOpportunities(scope as OpportunityScope)),
    [scope, refreshKey],
  );
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleApply = useCallback(
    async (offerId: number) => {
      setPendingId(offerId);
      setActionError(null);
      try {
        await applyToOpportunity(offerId);
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setPendingId(null);
      }
    },
    [refresh],
  );

  const handleToggleSave = useCallback(
    async (offerId: number, isSaved: boolean) => {
      setPendingId(offerId);
      setActionError(null);
      try {
        if (isSaved) {
          await unsaveOpportunity(offerId);
        } else {
          await saveOpportunity(offerId);
        }
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
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

      {scope === "auctions" && <AuctionsPanel />}
      {scope === "rewards" && <RewardsPanel />}
      {scope === "surveys" && <SurveysPanel />}

      {!NON_LIST_TABS.includes(scope) && actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}

      {!NON_LIST_TABS.includes(scope) && state.status === "loading" && (
        <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>
      )}
      {!NON_LIST_TABS.includes(scope) && state.status === "error" && (
        <EmptyState text="Не удалось загрузить возможности." />
      )}
      {!NON_LIST_TABS.includes(scope) && state.status === "ready" && state.data.length === 0 && (
        <EmptyState text="В этом разделе пока пусто." />
      )}
      {!NON_LIST_TABS.includes(scope) &&
        state.status === "ready" &&
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
