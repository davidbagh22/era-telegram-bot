import { useCallback, useEffect, useState } from "react";
import {
  applyToOpportunity,
  describeActionError,
  fetchOpportunities,
  saveOpportunity,
  unsaveOpportunity,
} from "../api/client";
import { BottomSheet } from "../components/BottomSheet";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { StatusBadge } from "../components/StatusBadge";
import { AuctionIcon, OpportunitiesIcon, RewardIcon, SurveyIcon } from "../components/icons";
import { useAsync } from "../hooks/useAsync";
import { AuctionsPanel } from "./opportunities/AuctionsPanel";
import { RewardsPanel } from "./opportunities/RewardsPanel";
import { SurveysPanel } from "./opportunities/SurveysPanel";
import type { OpportunityScope } from "../types/opportunity";

type OpportunitiesSection = "offers" | "auctions" | "rewards" | "surveys";

// 2026-08 redesign brief section 20 ("Возможности как премиальная
// витрина") + section 15 (no horizontal tabs as primary navigation): the
// old PillTabs row crammed 7 unrelated views (4 offer scopes + 3 entirely
// separate features) into one scrollable pill track. Auctions/Rewards/
// Surveys aren't filters of the same list — they're distinct feature
// areas, so they become landing cards, same pattern as ActivityScreen.
const SECTIONS: {
  value: OpportunitiesSection;
  label: string;
  description: string;
  Icon: typeof OpportunitiesIcon;
}[] = [
  { value: "offers", label: "Предложения", description: "Персональные и открытые предложения", Icon: OpportunitiesIcon },
  { value: "auctions", label: "Аукционы", description: "Ставки за баллы, лучший — побеждает", Icon: AuctionIcon },
  { value: "rewards", label: "Каталог", description: "Обменяйте баллы на награды", Icon: RewardIcon },
  { value: "surveys", label: "Опросы", description: "Поделитесь мнением с командой ЭРА", Icon: SurveyIcon },
];

const OFFER_SCOPES: { value: OpportunityScope; label: string }[] = [
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

// Once-only scroll-to/highlight duration for a per-notification deep
// link (`#/opportunities/{id}`) — matches TasksTab.tsx/EventsTab.tsx.
const HIGHLIGHT_MS = 2500;

interface OffersListProps {
  initialItemId?: number | null;
}

function OffersList({ initialItemId }: OffersListProps) {
  // A decided application (approved/rejected) — the case a deep link is
  // for — lives under "Мои заявки", not the "Для тебя" default.
  const [scope, setScope] = useState<OpportunityScope>(initialItemId ? "mine" : "for_me");
  const [showFilterSheet, setShowFilterSheet] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchOpportunities(scope), [scope, refreshKey]);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [highlightId, setHighlightId] = useState<number | null>(initialItemId ?? null);
  const scopeLabel = OFFER_SCOPES.find((option) => option.value === scope)?.label ?? scope;

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  useEffect(() => {
    if (highlightId === null || state.status !== "ready") {
      return;
    }
    document
      .getElementById(`opportunity-${highlightId}`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
    const timer = setTimeout(() => setHighlightId(null), HIGHLIGHT_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.status]);

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
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <strong>{scopeLabel}</strong>
        <button type="button" onClick={() => setShowFilterSheet(true)}>
          Фильтр
        </button>
      </div>

      <BottomSheet open={showFilterSheet} onClose={() => setShowFilterSheet(false)} title="Показать">
        <div style={{ display: "flex", flexDirection: "column" }}>
          {OFFER_SCOPES.map((option) => (
            <button
              key={option.value}
              type="button"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                width: "100%",
                textAlign: "left",
                fontFamily: "var(--era-font-body)",
                fontSize: "0.9375rem",
                padding: "0.625rem 0.25rem",
                border: "none",
                borderBottom: "1px solid var(--era-border)",
                background: "transparent",
                color: "var(--era-text)",
              }}
              onClick={() => {
                setScope(option.value);
                setShowFilterSheet(false);
              }}
            >
              <input type="radio" readOnly checked={scope === option.value} />
              {option.label}
            </button>
          ))}
        </div>
      </BottomSheet>

      {actionError && <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>}

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить возможности." />}
      {state.status === "ready" && state.data.length === 0 && (
        <EmptyState text="В этом разделе пока пусто." />
      )}
      {state.status === "ready" &&
        state.data.map((offer) => {
          const applied = offer.application_status === "pending" || offer.application_status === "approved";
          return (
            <div id={`opportunity-${offer.id}`} key={offer.id}>
              <Card style={offer.id === highlightId ? { boxShadow: "0 0 0 2px var(--era-violet)" } : undefined}>
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
            </div>
          );
        })}
    </div>
  );
}

interface OpportunitiesScreenProps {
  /** Set by App.tsx whenever the bot's "⭐ Возможности" quick-access
   * button or a per-notification deep link (`#/opportunities`,
   * `#/opportunities/{id}`) landed here — skips the landing menu and
   * goes straight to "Предложения", same as ActivityScreen skips its own
   * landing menu for `#/tasks`/`#/events`. `undefined` for a plain
   * bottom-nav tap, which does show the landing menu. */
  initialSection?: OpportunitiesSection;
  /** A specific offer id from a per-notification deep link
   * (`#/opportunities/{id}`) — passed through to the offers list once
   * it's showing, to scroll to and highlight it. */
  initialItemId?: number | null;
}

export function OpportunitiesScreen({ initialSection, initialItemId }: OpportunitiesScreenProps = {}) {
  const [section, setSection] = useState<OpportunitiesSection | null>(
    initialSection ?? (initialItemId ? "offers" : null),
  );

  if (section === null) {
    return (
      <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "1.375rem", margin: 0 }}>
          Возможности
        </h1>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {SECTIONS.map(({ value, label, description, Icon }) => (
            <Card key={value}>
              <button
                type="button"
                onClick={() => setSection(value)}
                style={{
                  all: "unset",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.875rem",
                  width: "100%",
                }}
              >
                <span
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: "2.75rem",
                    height: "2.75rem",
                    flexShrink: 0,
                    borderRadius: "var(--era-radius-control)",
                    background: "var(--era-gradient)",
                    color: "#fff",
                  }}
                  aria-hidden="true"
                >
                  <Icon />
                </span>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <strong style={{ display: "block", fontSize: "var(--era-text-lg)" }}>{label}</strong>
                  <span style={{ display: "block", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
                    {description}
                  </span>
                </span>
                <span aria-hidden="true" style={{ color: "var(--era-text-muted)" }}>
                  →
                </span>
              </button>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  const current = SECTIONS.find((item) => item.value === section);

  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <button type="button" onClick={() => setSection(null)}>
        ← Возможности
      </button>
      <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "1.375rem", margin: 0 }}>
        {current?.label}
      </h1>
      {section === "offers" && <OffersList initialItemId={section === "offers" ? initialItemId ?? null : null} />}
      {section === "auctions" && <AuctionsPanel />}
      {section === "rewards" && <RewardsPanel />}
      {section === "surveys" && <SurveysPanel />}
    </div>
  );
}
