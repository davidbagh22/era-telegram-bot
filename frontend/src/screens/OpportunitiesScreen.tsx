import { useCallback, useEffect, useMemo, useState } from "react";
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
import { PointsRulesSheet } from "./opportunities/PointsRulesSheet";
import { RewardsPanel } from "./opportunities/RewardsPanel";
import { SurveysPanel } from "./opportunities/SurveysPanel";

export type OpportunitiesSection = "offers" | "auctions" | "rewards" | "surveys";

const QUICK_STATES: { key: string; label: string; scope: OpportunityScope; state: OpportunityState | null }[] = [
  { key: "all", label: "Все", scope: "all", state: null },
  { key: "for_me", label: "Для тебя", scope: "for_me", state: null },
  { key: "available", label: "Доступно", scope: "all", state: "available" },
  { key: "almost", label: "Почти доступно", scope: "all", state: "almost" },
  { key: "mine", label: "Мои заявки", scope: "mine", state: null },
];

const TYPE_LABELS: Record<string, string> = {
  certificate: "Сертификат",
  letter: "Письмо",
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
  by_organization: "По организации",
  closing_soon: "Ближе всего к открытию",
  newest: "Новые",
};

const ISSUER_TONE: Record<string, string> = {
  "ЭРА": "Официальное подтверждение твоего вклада и роста внутри сообщества.",
  "Ассоциация студентов российских вузов в Армении": "Документы за общественную, волонтёрскую и лидерскую работу в студенческой среде.",
  "Дом Москвы в Ереване": "Признание вклада в молодёжные и общественно-культурные инициативы.",
  "КСООРС Армении": "Документы за вклад в общественную жизнь, сотрудничество и молодёжное движение соотечественников.",
};

const RECOGNITION_TYPES = new Set(["certificate", "letter"]);
const APPLIED_STATUSES = new Set(["pending", "requested", "under_review", "needs_info", "partner_review", "approved", "issued"]);
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
      window.localStorage.setItem(ACHIEVEMENT_SNAPSHOT_KEY, JSON.stringify({ availableIds, issuedIds }));
    } catch {
      return;
    }
    if (!previous) return;

    const newlyIssuedId = issuedIds.find((id) => !previous!.issuedIds.includes(id));
    if (newlyIssuedId !== undefined) {
      const offer = offers.find((item) => item.id === newlyIssuedId);
      if (offer) {
        setAchievement({
          kicker: "Достижение",
          title: "ДОКУМЕНТ ВЫДАН",
          description: `«${offer.title}» теперь подтверждает твой результат.`,
        });
      }
      return;
    }

    const unlockedId = availableIds.find((id) => !previous!.availableIds.includes(id));
    if (unlockedId !== undefined) {
      const offer = offers.find((item) => item.id === unlockedId);
      if (offer) {
        setAchievement({
          kicker: "Новая возможность",
          title: "ТЕПЕРЬ ДОСТУПНО",
          description: `Ты открыл «${offer.title}».`,
        });
      }
    }
  }, [offers, enabled]);

  return { achievement, dismiss: () => setAchievement(null) };
}

const EMPTY_FILTERS = {
  issuer: null as string | null,
  type: null as string | null,
  category: null as string | null,
};

function formatPoints(value: number): string {
  return new Intl.NumberFormat("ru-RU").format(value);
}

interface OffersListProps {
  initialItemId?: number | null;
}

function OffersList({ initialItemId }: OffersListProps) {
  // Full catalog is the default. "Для тебя" remains a separate curated view.
  const [scope, setScope] = useState<OpportunityScope>(initialItemId ? "mine" : "all");
  const [filters, setFilters] = useState<{
    issuer: string | null;
    type: string | null;
    category: string | null;
    status: OpportunityState | null;
  }>({ ...EMPTY_FILTERS, status: null });
  const [sort, setSort] = useState<OpportunitySort>("by_organization");
  const [showFilterSheet, setShowFilterSheet] = useState(false);
  const [draftFilters, setDraftFilters] = useState(filters);
  const [draftSort, setDraftSort] = useState<OpportunitySort>("by_organization");
  const [refreshKey, setRefreshKey] = useState(0);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(initialItemId ?? null);
  const [highlightId, setHighlightId] = useState<number | null>(initialItemId ?? null);
  const [actionError, setActionError] = useState<string | null>(null);

  const query: OpportunityFilters = {
    scope,
    state: filters.status,
    sort,
    issuer: filters.issuer,
    type: filters.type,
    category: filters.category,
  };
  const listState = useAsync(
    () => fetchOpportunities(query),
    [scope, filters.status, filters.issuer, filters.type, filters.category, sort, refreshKey],
  );
  const facetsState = useAsync(() => fetchOpportunityFacets(), []);
  const activeQuick = QUICK_STATES.find((item) => item.scope === scope && item.state === filters.status);
  const hasExtraFilters = Boolean(filters.issuer || filters.type || filters.category) || sort !== "by_organization";
  const achievement = useOpportunityAchievement(
    listState.status === "ready" ? listState.data : null,
    scope === "for_me",
  );

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const grouped = useMemo(() => {
    if (listState.status !== "ready" || scope !== "all" || filters.status) return null;
    const map = new Map<string, Opportunity[]>();
    for (const offer of listState.data) {
      const group = map.get(offer.partner_name) ?? [];
      group.push(offer);
      map.set(offer.partner_name, group);
    }
    return [...map.entries()];
  }, [listState.status, listState.status === "ready" ? listState.data : null, scope, filters.status]);

  const openFilterSheet = () => {
    setDraftFilters(filters);
    setDraftSort(sort);
    setShowFilterSheet(true);
  };

  const applyFilterSheet = () => {
    setFilters(draftFilters);
    setSort(draftSort);
    if (scope === "for_me" && (draftFilters.issuer || draftFilters.type || draftFilters.category)) {
      setScope("all");
    }
    setShowFilterSheet(false);
  };

  const resetAll = () => {
    const cleared = { ...EMPTY_FILTERS, status: null };
    setFilters(cleared);
    setDraftFilters(cleared);
    setSort("by_organization");
    setDraftSort("by_organization");
    setScope("all");
    setShowFilterSheet(false);
  };

  useEffect(() => {
    if (highlightId === null || listState.status !== "ready") return;
    document.getElementById(`opportunity-${highlightId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    const timer = setTimeout(() => setHighlightId(null), HIGHLIGHT_MS);
    return () => clearTimeout(timer);
  }, [highlightId, listState.status]);

  const handleApply = useCallback(async (offerId: number) => {
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
  }, [refresh]);

  const handleToggleSave = useCallback(async (offerId: number, isSaved: boolean) => {
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
  }, [refresh]);

  const renderCard = (offer: Opportunity, showIssuer: boolean) => (
    <OpportunityCard
      key={offer.id}
      offer={offer}
      showIssuer={showIssuer}
      expanded={expandedId === offer.id}
      highlighted={offer.id === highlightId}
      pending={pendingId === offer.id}
      onToggleExpanded={() => setExpandedId((current) => current === offer.id ? null : offer.id)}
      onApply={() => handleApply(offer.id)}
      onToggleSave={() => handleToggleSave(offer.id, offer.is_saved)}
    />
  );

  const recognitionCount = listState.status === "ready"
    ? listState.data.filter((offer) => RECOGNITION_TYPES.has(offer.opportunity_type)).length
    : 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
      <div style={{ display: "flex", gap: "0.5rem", overflowX: "auto", paddingBottom: "0.15rem" }}>
        {QUICK_STATES.map((option) => {
          const active = option.key === activeQuick?.key;
          return (
            <button
              key={option.key}
              type="button"
              onClick={() => {
                setScope(option.scope);
                setFilters((current) => ({ ...current, status: option.state }));
                if (option.key === "all") setSort("by_organization");
              }}
              style={{
                flexShrink: 0,
                padding: "0.48rem 0.82rem",
                borderRadius: "var(--era-radius-pill)",
                border: active ? "1px solid var(--era-violet)" : "1px solid var(--era-border)",
                background: active ? "var(--era-tint-violet)" : "var(--era-surface)",
                color: active ? "var(--era-violet)" : "var(--era-text)",
                fontWeight: 750,
                fontSize: "0.84rem",
              }}
            >
              {option.label}
            </button>
          );
        })}
      </div>

      <Card>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "flex-start" }}>
            <div>
              <MonoLabel tone="violet">Каталог признания</MonoLabel>
              <strong style={{ display: "block", marginTop: "0.25rem", fontSize: "1.05rem" }}>
                {scope === "all" && !filters.status ? "Все документы" : activeQuick?.label ?? "Возможности"}
              </strong>
              {listState.status === "ready" && (
                <span style={{ display: "block", marginTop: "0.2rem", color: "var(--era-text-muted)", fontSize: "0.8rem" }}>
                  {recognitionCount} документов в текущем списке
                </span>
              )}
            </div>
            <button type="button" onClick={openFilterSheet} style={{ flexShrink: 0 }}>
              Фильтры{hasExtraFilters ? " •" : ""}
            </button>
          </div>
          <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.82rem", lineHeight: 1.45 }}>
            Баллы — это порог подтверждённой активности. При получении документа они не списываются.
          </p>
        </div>
      </Card>

      <PointsRulesSheet />

      <BottomSheet open={showFilterSheet} onClose={() => setShowFilterSheet(false)} title="Фильтры">
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem", maxHeight: "60vh", overflowY: "auto" }}>
          <FilterGroup
            title="Организация"
            options={[{ value: null, label: "Все" }, ...(facetsState.status === "ready" ? facetsState.data.issuers.map((item) => ({ value: item, label: item })) : [])]}
            value={draftFilters.issuer}
            onChange={(value) => setDraftFilters((current) => ({ ...current, issuer: value }))}
          />
          <FilterGroup
            title="Тип"
            options={[{ value: null, label: "Все" }, ...(facetsState.status === "ready" ? facetsState.data.types.map((item) => ({ value: item, label: TYPE_LABELS[item] ?? item })) : [])]}
            value={draftFilters.type}
            onChange={(value) => setDraftFilters((current) => ({ ...current, type: value }))}
          />
          <FilterGroup
            title="Направление"
            options={[{ value: null, label: "Все" }, ...(facetsState.status === "ready" ? facetsState.data.categories.map((item) => ({ value: item, label: CATEGORY_LABELS[item] ?? item })) : [])]}
            value={draftFilters.category}
            onChange={(value) => setDraftFilters((current) => ({ ...current, category: value }))}
          />
          <FilterGroup
            title="Статус"
            options={[{ value: null, label: "Все" }, ...(Object.keys(STATE_LABELS) as OpportunityState[]).map((item) => ({ value: item, label: STATE_LABELS[item] }))]}
            value={draftFilters.status}
            onChange={(value) => setDraftFilters((current) => ({ ...current, status: value }))}
          />
          <FilterGroup
            title="Сортировка"
            options={(Object.keys(SORT_LABELS) as OpportunitySort[]).map((item) => ({ value: item, label: SORT_LABELS[item] }))}
            value={draftSort}
            onChange={(value) => setDraftSort((value ?? "by_organization") as OpportunitySort)}
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
          <button type="button" onClick={resetAll}>Показать весь каталог</button>
        </div>
      )}

      {grouped ? grouped.map(([issuer, offers]) => (
        <section key={issuer} style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
          <div style={{ padding: "0.25rem 0.1rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "baseline" }}>
              <strong style={{ fontSize: "1rem" }}>{issuer}</strong>
              <span style={{ color: "var(--era-text-muted)", fontSize: "0.78rem", whiteSpace: "nowrap" }}>{offers.length}</span>
            </div>
            {ISSUER_TONE[issuer] && (
              <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8rem", lineHeight: 1.4 }}>{ISSUER_TONE[issuer]}</p>
            )}
          </div>
          {offers.map((offer) => renderCard(offer, false))}
        </section>
      )) : listState.status === "ready" ? listState.data.map((offer) => renderCard(offer, true)) : null}

      {(scope === "for_me" || scope === "all") && (
        <details style={{ marginTop: "0.25rem" }}>
          <summary style={{ cursor: "pointer", fontWeight: 750 }}>Скоро в ЭРА</summary>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem", marginTop: "0.65rem" }}>
            {COMING_SOON.map(([title, description]) => (
              <Card key={title}>
                <strong>{title}</strong>
                <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "0.82rem" }}>{description}</p>
              </Card>
            ))}
          </div>
        </details>
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

function OpportunityCard({
  offer,
  showIssuer,
  expanded,
  highlighted,
  pending,
  onToggleExpanded,
  onApply,
  onToggleSave,
}: {
  offer: Opportunity;
  showIssuer: boolean;
  expanded: boolean;
  highlighted: boolean;
  pending: boolean;
  onToggleExpanded: () => void;
  onApply: () => void;
  onToggleSave: () => void;
}) {
  const recognition = RECOGNITION_TYPES.has(offer.opportunity_type);
  const applied = APPLIED_STATUSES.has(offer.application_status ?? "");
  const pointsCheck = offer.eligibility_checks.find((check) => check.key === "points");
  const currentPoints = pointsCheck ? Number(pointsCheck.current) || 0 : 0;
  const progressPercent = recognition && offer.required_points > 0
    ? Math.max(0, Math.min(100, Math.round((currentPoints / offer.required_points) * 100)))
    : null;
  // Current approved catalog only adds a non-points requirement for the
  // three volunteering degrees. Historical rank/metric checks are hidden
  // while the backend self-heals old rows on deploy.
  const visibleChecks = recognition
    ? offer.eligibility_checks.filter((check) => check.key === "points" || check.key === "metric:volunteer_hours")
    : offer.eligibility_checks;
  const volunteerCheck = visibleChecks.find((check) => check.key === "metric:volunteer_hours");
  const ctaLabel = applied
    ? null
    : recognition && !offer.eligible
      ? offer.state === "almost" ? "Осталось немного" : "Условия ещё не выполнены"
      : "Подать заявку";

  return (
    <div id={`opportunity-${offer.id}`}>
      <Card style={highlighted ? { boxShadow: "0 0 0 2px var(--era-violet)" } : undefined}>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
          {showIssuer && <MonoLabel tone="violet">{offer.partner_name.toUpperCase()}</MonoLabel>}

          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.55rem", alignItems: "flex-start" }}>
            <div style={{ minWidth: 0 }}>
              <strong style={{ display: "block", lineHeight: 1.28 }}>{offer.title}</strong>
              {recognition && (
                <span style={{ display: "block", marginTop: "0.28rem", color: "var(--era-violet)", fontSize: "0.8rem", fontWeight: 750 }}>
                  от {formatPoints(offer.required_points)} баллов
                  {volunteerCheck ? ` · ${volunteerCheck.required} ч. волонтёрства` : ""}
                </span>
              )}
            </div>
            {offer.application_status ? (
              <StatusBadge label={APPLICATION_STATUS_LABELS[offer.application_status] ?? offer.application_status} tone="violet" />
            ) : recognition ? (
              <StatusBadge label={STATE_LABELS[offer.state]} tone={offer.eligible ? "success" : "neutral"} />
            ) : null}
          </div>

          {recognition && progressPercent !== null && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.76rem", color: "var(--era-text-muted)", marginBottom: "0.25rem" }}>
                <span>{formatPoints(currentPoints)} / {formatPoints(offer.required_points)}</span>
                <span>{progressPercent}%</span>
              </div>
              <div style={{ height: 6, borderRadius: 999, background: "var(--era-surface-2)", overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${progressPercent}%`, background: "var(--era-gradient-signal)" }} />
              </div>
            </div>
          )}

          {!recognition && (
            <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.82rem" }}>
              {offer.description} · {offer.point_cost} баллов
            </p>
          )}

          <button type="button" onClick={onToggleExpanded} style={{ alignSelf: "flex-start" }}>
            {expanded ? "Скрыть" : "Подробнее"}
          </button>

          {expanded && (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
              {recognition && visibleChecks.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                  <span style={{ fontSize: "0.78rem", color: "var(--era-text-muted)" }}>Условия получения</span>
                  {visibleChecks.map((check) => (
                    <div key={check.key} style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", fontSize: "0.82rem" }}>
                      <span aria-hidden="true">{check.ok ? "✓" : "○"}</span>
                      <span style={{ color: check.ok ? "var(--era-text)" : "var(--era-text-muted)" }}>
                        {check.label}: {check.current} / нужно {check.required}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {recognition && (
                <div style={{ padding: "0.72rem", borderRadius: "var(--era-radius-control)", background: "var(--era-surface-2)" }}>
                  <span style={{ fontSize: "0.76rem", color: "var(--era-text-muted)" }}>Что фиксируется</span>
                  <p style={{ margin: "0.25rem 0 0", fontSize: "0.84rem", lineHeight: 1.4 }}>
                    Официальный документ · verified achievement · запись в портфолио · подтверждение опыта
                  </p>
                </div>
              )}

              {offer.reasons.length > 0 && (
                <p style={{ margin: 0, color: "var(--era-violet)", fontSize: "0.8rem" }}>{offer.reasons.join(" · ")}</p>
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
          )}
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
