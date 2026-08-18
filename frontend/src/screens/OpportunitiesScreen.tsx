import { useCallback, useEffect, useState } from "react";
import {
  applyToOpportunity,
  describeActionError,
  fetchOpportunities,
  fetchOpportunityFacets,
  saveOpportunity,
  unsaveOpportunity,
  type OpportunityFilters,
} from "../api/client";
import { AchievementOverlay } from "../components/AchievementOverlay";
import { BottomSheet } from "../components/BottomSheet";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { MonoLabel } from "../components/MonoLabel";
import { StatusBadge } from "../components/StatusBadge";
import { useAsync } from "../hooks/useAsync";
import type { Opportunity, OpportunityScope, OpportunitySort, OpportunityState } from "../types/opportunity";
import { AuctionsPanel } from "./opportunities/AuctionsPanel";
import { RewardsPanel } from "./opportunities/RewardsPanel";
import { SurveysPanel } from "./opportunities/SurveysPanel";

export type OpportunitiesSection = "offers" | "auctions" | "rewards" | "surveys";

// DELTA ToR §16 "Верхние быстрые состояния" -- each quick pill is a
// scope+state combination, not a new API concept.
const QUICK_STATES: { key: string; label: string; scope: OpportunityScope; state: OpportunityState | null }[] = [
  { key: "for_me", label: "Для тебя", scope: "for_me", state: null },
  { key: "available", label: "Доступно", scope: "all", state: "available" },
  { key: "almost", label: "Почти доступно", scope: "all", state: "almost" },
  { key: "mine", label: "Мои заявки", scope: "mine", state: null },
];

const TYPE_LABELS: Record<string, string> = {
  certificate: "Сертификат",
  letter: "Рекомендательное/благодарственное письмо",
  external: "Внешняя возможность",
};

const CATEGORY_LABELS: Record<string, string> = {
  projects: "Проекты",
  events: "Мероприятия",
  volunteering: "Волонтёрство",
  public_activity: "Общественная деятельность",
  media: "Медиа",
  leadership: "Лидерство",
  international: "Международная/партнёрская деятельность",
};

const STATE_LABELS: Record<OpportunityState, string> = {
  available: "Доступно",
  almost: "Почти доступно",
  closed: "Закрыто",
  requested: "Заявка отправлена",
  review: "На рассмотрении",
  issued: "Выдано",
};

const SORT_LABELS: Record<OpportunitySort, string> = {
  closing_soon: "Ближе всего к открытию",
  newest: "Новые",
  by_organization: "По организации",
};

// DELTA ToR §26: official document titles never change -- this is only the
// supporting line above them, one per issuer.
const ISSUER_TONE: Record<string, string> = {
  "ЭРА": "Твой вклад уже есть. Теперь его можно зафиксировать как реальный подтверждённый опыт.",
  "Дом Москвы в Ереване": "Для тех, кто не просто приходит на события, а помогает создавать молодёжные и культурные проекты.",
  "КСООРС Армении": "Подтверждение реального общественного вклада в жизнь сообщества — через проекты, инициативы и ответственность.",
  "Ассоциация студентов российских вузов в Армении": "Твоя работа в студенческой среде может стать частью портфолио, а не остаться просто хорошим воспоминанием.",
};

const RECOGNITION_BENEFITS = ["официальный документ", "verified achievement", "запись в портфолио", "подтверждение опыта"];

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

const EMPTY_FILTERS = { issuer: null as string | null, type: null as string | null, category: null as string | null };

function OffersList({ initialItemId }: OffersListProps) {
  const [scope, setScope] = useState<OpportunityScope>(initialItemId ? "mine" : "for_me");
  const [filters, setFilters] = useState<{ issuer: string | null; type: string | null; category: string | null; status: OpportunityState | null }>({
    ...EMPTY_FILTERS,
    status: null,
  });
  const [sort, setSort] = useState<OpportunitySort>("closing_soon");
  const [showFilterSheet, setShowFilterSheet] = useState(false);
  const [draftFilters, setDraftFilters] = useState(filters);
  const [draftSort, setDraftSort] = useState<OpportunitySort>("closing_soon");
  const [refreshKey, setRefreshKey] = useState(0);
  const query: OpportunityFilters = { scope, state: filters.status, sort, issuer: filters.issuer, type: filters.type, category: filters.category };
  const listState = useAsync(
    () => fetchOpportunities(query),
    [scope, filters.status, filters.issuer, filters.type, filters.category, sort, refreshKey],
  );
  const facetsState = useAsync(() => fetchOpportunityFacets(), []);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [highlightId, setHighlightId] = useState<number | null>(initialItemId ?? null);
  const activeQuick = QUICK_STATES.find((q) => q.scope === scope && q.state === filters.status);
  const hasExtraFilters = Boolean(filters.issuer || filters.type || filters.category) || sort !== "closing_soon";
  const achievement = useOpportunityAchievement(
    listState.status === "ready" ? listState.data : null,
    scope === "for_me",
  );

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const openFilterSheet = () => {
    setDraftFilters(filters);
    setDraftSort(sort);
    setShowFilterSheet(true);
  };

  const applyFilterSheet = () => {
    setFilters(draftFilters);
    setSort(draftSort);
    // "Для тебя" is a small curated top pick, not the full catalog -- once
    // someone picks a real facet (issuer/type/category), they're browsing,
    // not asking for a recommendation, so switch to the full "Все" list.
    // Otherwise a filter could silently return nothing just because the
    // matching item wasn't among the handful of top picks.
    if (scope === "for_me" && (draftFilters.issuer || draftFilters.type || draftFilters.category)) {
      setScope("all");
    }
    setShowFilterSheet(false);
  };

  const resetAll = () => {
    const cleared = { ...EMPTY_FILTERS, status: null };
    setFilters(cleared);
    setDraftFilters(cleared);
    setSort("closing_soon");
    setDraftSort("closing_soon");
    setScope("for_me");
    setShowFilterSheet(false);
  };

  useEffect(() => {
    if (highlightId === null || listState.status !== "ready") return;
    document.getElementById(`opportunity-${highlightId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    const timer = setTimeout(() => setHighlightId(null), HIGHLIGHT_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listState.status]);

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
      <div style={{ display: "flex", gap: "0.5rem", overflowX: "auto", paddingBottom: "0.15rem" }}>
        {QUICK_STATES.map((option) => {
          const active = option.key === activeQuick?.key;
          return (
            <button
              key={option.key}
              type="button"
              onClick={() => { setScope(option.scope); setFilters((f) => ({ ...f, status: option.state })); }}
              style={{
                flexShrink: 0,
                padding: "0.45rem 0.85rem",
                borderRadius: "var(--era-radius-pill)",
                border: active ? "1px solid var(--era-violet)" : "1px solid var(--era-border)",
                background: active ? "var(--era-tint-violet)" : "var(--era-surface)",
                color: active ? "var(--era-violet)" : "var(--era-text)",
                fontWeight: 700,
                fontSize: "0.85rem",
              }}
            >
              {option.label}
            </button>
          );
        })}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
          Реальные действия открывают реальные возможности.
        </p>
        <button type="button" onClick={openFilterSheet} style={{ flexShrink: 0 }}>
          Фильтры{hasExtraFilters ? " •" : ""}
        </button>
      </div>

      <BottomSheet open={showFilterSheet} onClose={() => setShowFilterSheet(false)} title="Фильтры">
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem", maxHeight: "60vh", overflowY: "auto" }}>
          <FilterGroup
            title="Организация"
            options={[{ value: null, label: "Все" }, ...(facetsState.status === "ready" ? facetsState.data.issuers.map((i) => ({ value: i, label: i })) : [])]}
            value={draftFilters.issuer}
            onChange={(v) => setDraftFilters((f) => ({ ...f, issuer: v }))}
          />
          <FilterGroup
            title="Тип"
            options={[{ value: null, label: "Все" }, ...(facetsState.status === "ready" ? facetsState.data.types.map((t) => ({ value: t, label: TYPE_LABELS[t] ?? t })) : [])]}
            value={draftFilters.type}
            onChange={(v) => setDraftFilters((f) => ({ ...f, type: v }))}
          />
          <FilterGroup
            title="Направление результата"
            options={[{ value: null, label: "Все" }, ...(facetsState.status === "ready" ? facetsState.data.categories.map((c) => ({ value: c, label: CATEGORY_LABELS[c] ?? c })) : [])]}
            value={draftFilters.category}
            onChange={(v) => setDraftFilters((f) => ({ ...f, category: v }))}
          />
          <FilterGroup
            title="Статус"
            options={[{ value: null, label: "Все" }, ...(Object.keys(STATE_LABELS) as OpportunityState[]).map((s) => ({ value: s, label: STATE_LABELS[s] }))]}
            value={draftFilters.status}
            onChange={(v) => setDraftFilters((f) => ({ ...f, status: v }))}
          />
          <FilterGroup
            title="Сортировка"
            options={(Object.keys(SORT_LABELS) as OpportunitySort[]).map((s) => ({ value: s, label: SORT_LABELS[s] }))}
            value={draftSort}
            onChange={(v) => setDraftSort((v ?? "closing_soon") as OpportunitySort)}
          />
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button type="button" onClick={resetAll} style={{ flex: 1 }}>Сбросить</button>
            <button type="button" className="era-btn-primary" onClick={applyFilterSheet} style={{ flex: 1 }}>Показать</button>
          </div>
        </div>
      </BottomSheet>

      {actionError && <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>}
      {listState.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {listState.status === "error" && <EmptyState text="Не удалось загрузить возможности." />}
      {listState.status === "ready" && listState.data.length === 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", alignItems: "flex-start" }}>
          <EmptyState text="По этим параметрам пока ничего нет" />
          <button type="button" onClick={resetAll}>Сбросить фильтры</button>
        </div>
      )}

      {listState.status === "ready" && listState.data.map((offer) => (
        <OpportunityCard
          key={offer.id}
          offer={offer}
          highlighted={offer.id === highlightId}
          pending={pendingId === offer.id}
          onApply={() => handleApply(offer.id)}
          onToggleSave={() => handleToggleSave(offer.id, offer.is_saved)}
        />
      ))}

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

function FilterGroup<T extends string>({
  title,
  options,
  value,
  onChange,
}: {
  title: string;
  options: { value: T | null; label: string }[];
  value: T | null;
  onChange: (value: T | null) => void;
}) {
  return (
    <div>
      <strong style={{ display: "block", marginBottom: "0.4rem", fontSize: "0.9rem" }}>{title}</strong>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
        {options.map((option) => {
          const active = option.value === value;
          return (
            <button
              key={option.label}
              type="button"
              onClick={() => onChange(option.value)}
              style={{
                padding: "0.4rem 0.7rem",
                borderRadius: "var(--era-radius-pill)",
                border: active ? "1px solid var(--era-violet)" : "1px solid var(--era-border)",
                background: active ? "var(--era-tint-violet)" : "var(--era-surface-2)",
                color: active ? "var(--era-violet)" : "var(--era-text)",
                fontSize: "0.8rem",
                fontWeight: 650,
              }}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

const APPLIED_STATUSES = new Set(["pending", "requested", "under_review", "needs_info", "partner_review", "approved", "issued"]);

/**
 * ToR §25: "не цену сертификата, а следующий уровень своего пути" -- issuer
 * header, human-meaning line, progress toward the points threshold,
 * condition checklist, what it confirms/what you get, then a single CTA.
 */
function OpportunityCard({
  offer,
  highlighted,
  pending,
  onApply,
  onToggleSave,
}: {
  offer: Opportunity;
  highlighted: boolean;
  pending: boolean;
  onApply: () => void;
  onToggleSave: () => void;
}) {
  const recognition = offer.opportunity_type === "certificate" || offer.opportunity_type === "letter";
  const applied = APPLIED_STATUSES.has(offer.application_status ?? "");
  const isAvailable = offer.state === "available";
  const cardStyle = highlighted
    ? { boxShadow: "0 0 0 2px var(--era-violet)" }
    : isAvailable
      ? { background: "var(--era-hero-bg)", border: "1px solid rgba(99,44,255,0.18)", boxShadow: "var(--era-glow-violet)" }
      : undefined;

  const pointsCheck = offer.eligibility_checks.find((check) => check.key === "points");
  const currentPoints = pointsCheck ? Number(pointsCheck.current) || 0 : 0;
  const progressPercent = recognition && offer.required_points > 0
    ? Math.max(0, Math.min(100, Math.round((currentPoints / offer.required_points) * 100)))
    : null;

  const ctaLabel = applied
    ? null
    : recognition && !offer.eligible
      ? offer.state === "almost" ? "Осталось немного" : "Условия ещё не выполнены"
      : "Подать заявку";

  return (
    <div id={`opportunity-${offer.id}`}>
      <Card style={cardStyle}>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
          <MonoLabel tone="violet">{offer.partner_name.toUpperCase()}</MonoLabel>
          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", alignItems: "flex-start" }}>
            <strong style={{ display: "block" }}>{offer.title}</strong>
            {offer.application_status ? (
              <StatusBadge label={APPLICATION_STATUS_LABELS[offer.application_status] ?? offer.application_status} tone="violet" />
            ) : recognition ? (
              <StatusBadge label={STATE_LABELS[offer.state]} tone={offer.eligible ? "success" : "neutral"} />
            ) : null}
          </div>

          {ISSUER_TONE[offer.partner_name] && (
            <p style={{ margin: 0, fontWeight: 650, lineHeight: 1.4 }}>{ISSUER_TONE[offer.partner_name]}</p>
          )}

          {recognition && progressPercent !== null && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.78rem", color: "var(--era-text-muted)", marginBottom: "0.25rem" }}>
                <span>{currentPoints} / {offer.required_points}</span>
                <span>{progressPercent}%</span>
              </div>
              <div style={{ height: 6, borderRadius: 999, background: "var(--era-surface-2)", overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${progressPercent}%`, background: "var(--era-gradient-signal)" }} />
              </div>
            </div>
          )}

          {!recognition && (
            <>
              <p style={{ margin: 0, color: "var(--era-text-muted)" }}>{offer.description}</p>
              <p style={{ margin: 0, color: "var(--era-text-muted)" }}>
                {offer.point_cost} баллов · мест: {offer.remaining_slots}
              </p>
            </>
          )}

          {recognition && offer.eligibility_checks.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
              <span style={{ fontSize: "0.78rem", color: "var(--era-text-muted)" }}>Условия</span>
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

          {recognition && (
            <div style={{ padding: "0.7rem", borderRadius: "var(--era-radius-control)", background: "var(--era-surface-2)" }}>
              <span style={{ fontSize: "0.78rem", color: "var(--era-text-muted)" }}>Что получишь</span>
              <p style={{ margin: "0.25rem 0 0", fontSize: "0.85rem" }}>{RECOGNITION_BENEFITS.join(" · ")}</p>
            </div>
          )}

          {offer.reasons.length > 0 && (
            <p style={{ margin: 0, color: "var(--era-violet)", fontSize: "0.8125rem" }}>{offer.reasons.join(" · ")}</p>
          )}

          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            {ctaLabel && (
              <button
                type="button"
                className="era-btn-primary"
                disabled={pending || (recognition && !offer.eligible)}
                onClick={onApply}
              >
                {ctaLabel}
              </button>
            )}
            <button type="button" disabled={pending} onClick={onToggleSave}>
              {offer.is_saved ? "Убрать из сохранённых" : "Сохранить"}
            </button>
          </div>
        </div>
      </Card>
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
    <div className="era-page" style={{ padding: "1.25rem 1.25rem var(--era-page-bottom-safe)", display: "flex", flexDirection: "column", gap: "1rem" }}>
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
