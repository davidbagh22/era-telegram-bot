import { useCallback, useEffect, useState } from "react";
import {
  applyToOpportunity,
  describeActionError,
  fetchOpportunities,
  saveOpportunity,
  unsaveOpportunity,
} from "../api/client";
import { AchievementOverlay } from "../components/AchievementOverlay";
import { BottomSheet } from "../components/BottomSheet";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { MonoLabel } from "../components/MonoLabel";
import { StatusBadge } from "../components/StatusBadge";
import { useAsync } from "../hooks/useAsync";
import type { Opportunity, OpportunityDisplayState, OpportunityScope } from "../types/opportunity";
import { AuctionsPanel } from "./opportunities/AuctionsPanel";
import { RewardsPanel } from "./opportunities/RewardsPanel";
import { SurveysPanel } from "./opportunities/SurveysPanel";

export type OpportunitiesSection = "offers" | "auctions" | "rewards" | "surveys";

const OFFER_SCOPES: { value: OpportunityScope; label: string }[] = [
  { value: "for_me", label: "Для тебя" },
  { value: "all", label: "Все" },
  { value: "saved", label: "Сохранённые" },
  { value: "mine", label: "Мои заявки" },
];

const APPLICATION_STATUS_LABELS: Record<string, string> = {
  pending: "на проверке",
  requested: "заявка отправлена",
  under_review: "проверка ЭРА",
  needs_info: "нужна информация",
  partner_review: "проверка партнёра",
  approved: "одобрено",
  issued: "выдано",
  rejected: "отклонено",
};

const DISPLAY_STATE_META: Record<OpportunityDisplayState, { label: string; tone: "neutral" | "violet" | "gold" | "success" }> = {
  locked: { label: "Закрыто", tone: "neutral" },
  almost: { label: "Почти доступно", tone: "gold" },
  available: { label: "Доступно", tone: "success" },
  new: { label: "Новое", tone: "violet" },
};

const COMING_SOON = [
  ["Форумы и поездки", "Отбор на молодёжные форумы и внешние программы."],
  ["Стажировки и практика", "Реальный профессиональный опыт у партнёров."],
  ["Закрытые встречи", "Спикеры, эксперты и партнёры."],
  ["Образовательные программы", "Курсы, мастер-классы и программы развития."],
  ["Делегации и представительство", "Представление ЭРА на внешних площадках."],
  ["Гранты и конкурсы", "Сильные проекты и внешние конкурсные возможности."],
  ["Наставничество", "Работа с сильными лидерами и экспертами."],
] as const;

const HIGHLIGHT_MS = 2500;
const ACHIEVEMENT_SNAPSHOT_KEY = "era.opportunities.achievementSnapshot";

type OpportunityAchievement = {
  kicker: string;
  title: string;
  description: string;
} | null;

function useOpportunityAchievement(offers: Opportunity[] | null, enabled: boolean) {
  const [achievement, setAchievement] = useState<OpportunityAchievement>(null);

  useEffect(() => {
    // Only the personalised "Для тебя" feed is allowed to mutate the
    // achievement baseline. Saved/mine/all are different projections of the
    // same data and switching filters must never look like a fresh unlock.
    if (!offers || !enabled) return;
    const availableIds = offers
      .filter((offer) => offer.display_state === "available" || offer.display_state === "new")
      .map((offer) => offer.id);
    const issuedIds = offers
      .filter((offer) => offer.application_status === "issued")
      .map((offer) => offer.id);

    let previous: { availableIds: number[]; issuedIds: number[] } | null = null;
    try {
      const raw = window.localStorage.getItem(ACHIEVEMENT_SNAPSHOT_KEY);
      previous = raw ? JSON.parse(raw) : null;
    } catch {
      return;
    }

    try {
      window.localStorage.setItem(ACHIEVEMENT_SNAPSHOT_KEY, JSON.stringify({ availableIds, issuedIds }));
    } catch {
      return;
    }

    // First visit only establishes a baseline. Signal mode is reserved for
    // a real transition, never for every already-existing opportunity.
    if (!previous) return;

    const newlyIssuedId = issuedIds.find((id) => !previous!.issuedIds.includes(id));
    if (newlyIssuedId !== undefined) {
      const offer = offers.find((item) => item.id === newlyIssuedId);
      if (offer) {
        setAchievement({
          kicker: "Достижение",
          title: "ДОКУМЕНТ ВЫДАН",
          description: `«${offer.title}» теперь подтверждает твой результат в ЭРА.`,
        });
        return;
      }
    }

    const unlockedId = availableIds.find((id) => !previous!.availableIds.includes(id));
    if (unlockedId !== undefined) {
      const offer = offers.find((item) => item.id === unlockedId);
      if (offer) {
        setAchievement({
          kicker: "Новая возможность",
          title: "ТЕПЕРЬ ДОСТУПНО",
          description: `Ты открыл «${offer.title}». Это результат твоей активности.`,
        });
      }
    }
  }, [offers, enabled]);

  return { achievement, dismiss: () => setAchievement(null) };
}

interface OffersListProps {
  initialItemId?: number | null;
}

function OffersList({ initialItemId }: OffersListProps) {
  const [scope, setScope] = useState<OpportunityScope>(initialItemId ? "mine" : "for_me");
  const [showFilterSheet, setShowFilterSheet] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchOpportunities(scope), [scope, refreshKey]);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [highlightId, setHighlightId] = useState<number | null>(initialItemId ?? null);
  const scopeLabel = OFFER_SCOPES.find((option) => option.value === scope)?.label ?? scope;
  const achievement = useOpportunityAchievement(
    state.status === "ready" ? state.data : null,
    scope === "for_me",
  );

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  useEffect(() => {
    if (highlightId === null || state.status !== "ready") return;
    document.getElementById(`opportunity-${highlightId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
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
        if (isSaved) await unsaveOpportunity(offerId);
        else await saveOpportunity(offerId);
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
    <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <strong>{scopeLabel}</strong>
          <p style={{ margin: "0.15rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
            Реальные действия открывают реальные возможности.
          </p>
        </div>
        <button type="button" onClick={() => setShowFilterSheet(true)}>Фильтр</button>
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
      {state.status === "ready" && state.data.length === 0 && <EmptyState text="В этом разделе пока пусто." />}

      {state.status === "ready" && state.data.map((offer) => {
        const recognition = offer.opportunity_type === "certificate" || offer.opportunity_type === "letter";
        const applied = ["pending", "requested", "under_review", "needs_info", "partner_review", "approved", "issued"].includes(offer.application_status ?? "");
        const stateMeta = DISPLAY_STATE_META[offer.display_state];
        const stateStyle = {
          locked: { background: "var(--era-surface)", opacity: 0.88 },
          almost: { background: "var(--era-tint-gold, var(--era-surface-2))", border: "1px solid rgba(244,193,93,0.42)" },
          available: { background: "var(--era-hero-bg)", border: "1px solid rgba(99,44,255,0.18)", boxShadow: "var(--era-glow-violet)" },
          new: { background: "var(--era-gradient-signal-soft, var(--era-hero-bg))", border: "1px solid rgba(215,25,120,0.24)", boxShadow: "var(--era-glow-hot)" },
        }[offer.display_state];
        const cardStyle = offer.id === highlightId
          ? { ...stateStyle, boxShadow: "0 0 0 2px var(--era-violet)" }
          : stateStyle;
        return (
          <div id={`opportunity-${offer.id}`} key={offer.id}>
            <Card style={cardStyle}>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", alignItems: "flex-start" }}>
                  <div>
                    <strong style={{ display: "block" }}>{offer.title}</strong>
                    <span style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>{offer.partner_name}</span>
                  </div>
                  {offer.application_status ? (
                    <StatusBadge label={APPLICATION_STATUS_LABELS[offer.application_status] ?? offer.application_status} tone="violet" />
                  ) : (
                    <StatusBadge label={stateMeta.label} tone={stateMeta.tone} />
                  )}
                </div>

                <p style={{ margin: 0, color: "var(--era-text-muted)" }}>{offer.description}</p>

                {recognition ? (
                  <div style={{ padding: "0.75rem", borderRadius: "var(--era-radius-control)", background: "var(--era-surface-2)" }}>
                    <strong>Требуется: {offer.required_points} баллов</strong>
                    <p style={{ margin: "0.2rem 0 0", fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>
                      Баллы — накопленная репутация. При получении документа они не списываются.
                    </p>
                  </div>
                ) : (
                  <p style={{ margin: 0, color: "var(--era-text-muted)" }}>
                    Условие внешнего предложения: {offer.point_cost} баллов · мест: {offer.remaining_slots}
                  </p>
                )}

                {recognition && offer.eligibility_checks.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                    {offer.eligibility_checks.map((check) => (
                      <div key={check.key} style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", fontSize: "0.8125rem" }}>
                        <span aria-hidden="true">{check.ok ? "✓" : "○"}</span>
                        <span style={{ color: check.ok ? "var(--era-text)" : "var(--era-text-muted)" }}>
                          {check.label}: {check.current} / нужно {check.required}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {offer.reasons.length > 0 && (
                  <p style={{ margin: 0, color: "var(--era-violet)", fontSize: "0.8125rem" }}>{offer.reasons.join(" · ")}</p>
                )}

                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  {!applied && (
                    <button
                      type="button"
                      className="era-btn-primary"
                      disabled={pendingId === offer.id || !offer.eligible}
                      onClick={() => handleApply(offer.id)}
                    >
                      {offer.display_state === "almost"
                        ? "Остался один шаг"
                        : !offer.eligible
                          ? "Условия ещё не выполнены"
                          : "Подать заявку"}
                    </button>
                  )}
                  <button type="button" disabled={pendingId === offer.id} onClick={() => handleToggleSave(offer.id, offer.is_saved)}>
                    {offer.is_saved ? "Убрать из сохранённых" : "Сохранить"}
                  </button>
                </div>
              </div>
            </Card>
          </div>
        );
      })}

      {(scope === "for_me" || scope === "all") && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem", marginTop: "0.4rem" }}>
          <div>
            <strong>Скоро в ЭРА</strong>
            <p style={{ margin: "0.15rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
              Уже в развитии. Заявок пока нет — появятся только вместе с реальным процессом отбора.
            </p>
          </div>
          {COMING_SOON.map(([title, description]) => (
            <Card key={title}>
              <strong>{title}</strong>
              <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>{description}</p>
              <p style={{ margin: "0.4rem 0 0", color: "var(--era-violet)", fontSize: "0.8125rem" }}>Ожидается в скором времени</p>
            </Card>
          ))}
        </div>
      )}

      <AchievementOverlay
        open={achievement.achievement !== null}
        onClose={achievement.dismiss}
        kicker={achievement.achievement?.kicker}
        title={achievement.achievement?.title ?? ""}
        description={achievement.achievement?.description}
      />
    </div>
  );
}

interface OpportunitiesScreenProps {
  initialSection?: OpportunitiesSection;
  initialItemId?: number | null;
  onBack?: () => void;
}

export function OpportunitiesScreen({ initialSection = "offers", initialItemId, onBack }: OpportunitiesScreenProps = {}) {
  const section = initialSection;
  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      {onBack && <button type="button" onClick={onBack}>← Сообщество</button>}
      <div>
        <MonoLabel tone="violet">Следующий уровень</MonoLabel>
        <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "1.75rem", fontWeight: 800, margin: "0.35rem 0 0" }}>Возможности</h1>
      </div>
      {section === "offers" && <OffersList initialItemId={initialItemId ?? null} />}
      {section === "auctions" && <AuctionsPanel />}
      {section === "rewards" && <RewardsPanel />}
      {section === "surveys" && <SurveysPanel />}
    </div>
  );
}
