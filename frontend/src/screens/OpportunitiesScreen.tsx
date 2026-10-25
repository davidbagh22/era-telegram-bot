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
type QuickKey = "all" | "for_me" | "available" | "almost";
type UiSort = "recommended" | "closing_soon" | "newest" | "required_points";

const STORAGE_KEY = "era.opportunities.state.v2";

const QUICK_STATES: { key: QuickKey; label: string; scope: OpportunityScope; state: OpportunityState | null }[] = [
  { key: "all", label: "Все", scope: "all", state: null },
  { key: "for_me", label: "Для тебя", scope: "for_me", state: null },
  { key: "available", label: "Доступно", scope: "all", state: "available" },
  { key: "almost", label: "Скоро доступно", scope: "all", state: "almost" },
];

const STATE_LABELS: Record<OpportunityState, string> = {
  available: "Доступно",
  almost: "Скоро доступно",
  closed: "Закрыто",
  requested: "Заявка отправлена",
  review: "На рассмотрении",
  issued: "Выдано",
};

const UI_SORT_LABELS: Record<UiSort, string> = {
  recommended: "Рекомендованные",
  closing_soon: "Ближайшие",
  newest: "Новые",
  required_points: "По требуемым баллам",
};

const CATEGORY_LABELS: Record<string, string> = {
  recognition: "Признание и документы",
  documents: "Признание и документы",
  education: "Образовательные программы",
  delegations: "Делегации",
  grants: "Гранты и конкурсы",
  competitions: "Гранты и конкурсы",
  era_pro: "ЭРА PRO",
  events: "Мероприятия",
  other: "Другое",
  projects: "Проекты",
  volunteering: "Волонтёрство",
  media: "Медиа",
  leadership: "Лидерство",
  international: "Международные возможности",
};

const APPLICATION_STATUS_LABELS: Record<string, string> = {
  pending: "Заявка рассматривается",
  requested: "Заявка отправлена",
  under_review: "Заявка рассматривается",
  needs_info: "Нужно дополнить",
  partner_review: "На рассмотрении партнёра",
  approved: "Одобрено",
  issued: "Выдано",
  rejected: "Отклонено",
};

const APPLIED_STATUSES = new Set(["pending", "requested", "under_review", "needs_info", "partner_review", "approved", "issued"]);

interface StoredState {
  scope: OpportunityScope;
  status: OpportunityState | null;
  category: string | null;
  sort: UiSort;
  scrollY: number;
}

function loadStoredState(): StoredState | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) as StoredState : null;
  } catch {
    return null;
  }
}

function backendSort(sort: UiSort): OpportunitySort {
  if (sort === "newest") return "newest";
  if (sort === "closing_soon") return "closing_soon";
  return "by_organization";
}

function sortClient(items: Opportunity[], sort: UiSort): Opportunity[] {
  if (sort === "required_points") return [...items].sort((a, b) => a.required_points - b.required_points);
  if (sort === "recommended") {
    return [...items].sort((a, b) => {
      const reasons = b.reasons.length - a.reasons.length;
      if (reasons !== 0) return reasons;
      if (a.eligible !== b.eligible) return a.eligible ? -1 : 1;
      return a.required_points - b.required_points;
    });
  }
  return items;
}

function formatPoints(value: number): string {
  return new Intl.NumberFormat("ru-RU").format(value);
}

function OffersList({ initialItemId }: { initialItemId?: number | null }) {
  const stored = useMemo(() => loadStoredState(), []);
  const [scope, setScope] = useState<OpportunityScope>(initialItemId ? "mine" : stored?.scope ?? "all");
  const [status, setStatus] = useState<OpportunityState | null>(initialItemId ? null : stored?.status ?? null);
  const [category, setCategory] = useState<string | null>(stored?.category ?? null);
  const [sort, setSort] = useState<UiSort>(stored?.sort ?? "recommended");
  const [showFilterSheet, setShowFilterSheet] = useState(false);
  const [draftCategory, setDraftCategory] = useState<string | null>(category);
  const [draftStatus, setDraftStatus] = useState<OpportunityState | null>(status);
  const [draftSort, setDraftSort] = useState<UiSort>(sort);
  const [refreshKey, setRefreshKey] = useState(0);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(initialItemId ?? null);
  const [actionError, setActionError] = useState<string | null>(null);

  const query: OpportunityFilters = {
    scope,
    state: status,
    sort: backendSort(sort),
    issuer: null,
    type: null,
    category,
  };
  const listState = useAsync(() => fetchOpportunities(query), [scope, status, category, sort, refreshKey]);
  const facetsState = useAsync(() => fetchOpportunityFacets(), []);
  const previewState = useAsync(
    () => showFilterSheet
      ? fetchOpportunities({ scope, state: draftStatus, sort: backendSort(draftSort), issuer: null, type: null, category: draftCategory })
      : Promise.resolve([] as Opportunity[]),
    [showFilterSheet, scope, draftStatus, draftCategory, draftSort],
  );

  const offers = useMemo(
    () => listState.status === "ready" ? sortClient(listState.data, sort) : [],
    [listState, sort],
  );
  const activeQuick = QUICK_STATES.find((item) => item.scope === scope && item.state === status)?.key ?? null;
  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  useEffect(() => {
    const restore = stored?.scrollY ?? 0;
    if (restore <= 0) return;
    const frame = window.requestAnimationFrame(() => window.scrollTo({ top: restore, behavior: "auto" }));
    return () => window.cancelAnimationFrame(frame);
  }, [stored]);

  useEffect(() => {
    const save = () => {
      try {
        window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ scope, status, category, sort, scrollY: window.scrollY } satisfies StoredState));
      } catch {
        // Embedded/private modes may disable storage. Filtering still works.
      }
    };
    window.addEventListener("pagehide", save);
    return () => {
      save();
      window.removeEventListener("pagehide", save);
    };
  }, [scope, status, category, sort]);

  useEffect(() => {
    if (!initialItemId || listState.status !== "ready") return;
    const frame = window.requestAnimationFrame(() => document.getElementById(`opportunity-${initialItemId}`)?.scrollIntoView({ block: "center" }));
    return () => window.cancelAnimationFrame(frame);
  }, [initialItemId, listState.status]);

  const chooseQuick = (key: QuickKey) => {
    const option = QUICK_STATES.find((item) => item.key === key)!;
    setScope(option.scope);
    setStatus(option.state);
    if (key === "for_me") setSort("recommended");
  };

  const openFilters = () => {
    setDraftCategory(category);
    setDraftStatus(status);
    setDraftSort(sort);
    setShowFilterSheet(true);
  };

  const applyFilters = () => {
    setCategory(draftCategory);
    setStatus(draftStatus);
    setSort(draftSort);
    setShowFilterSheet(false);
  };

  const resetFilters = () => {
    setDraftCategory(null);
    setDraftStatus(null);
    setDraftSort("recommended");
  };

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

  const handleSave = useCallback(async (offer: Opportunity) => {
    setPendingId(offer.id);
    setActionError(null);
    try {
      if (offer.is_saved) await unsaveOpportunity(offer.id);
      else await saveOpportunity(offer.id);
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setPendingId(null);
    }
  }, [refresh]);

  const categories = facetsState.status === "ready" ? facetsState.data.categories : [];
  const previewCount = previewState.status === "ready" ? previewState.data.length : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.55rem" }}>
        {QUICK_STATES.map((option) => {
          const active = option.key === activeQuick;
          return (
            <button
              key={option.key}
              type="button"
              onClick={() => chooseQuick(option.key)}
              style={{
                minWidth: 0,
                padding: "0.7rem 0.65rem",
                borderRadius: "var(--era-radius-control)",
                border: active ? "1px solid var(--era-violet)" : "1px solid var(--era-border)",
                background: active ? "var(--era-tint-violet)" : "var(--era-surface)",
                color: active ? "var(--era-violet)" : "var(--era-text)",
                fontWeight: 800,
                fontSize: "0.84rem",
              }}
            >
              {option.label}
            </button>
          );
        })}
      </div>

      <Card style={{ padding: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.8rem" }}>
          <div>
            <MonoLabel tone="violet">Каталог возможностей</MonoLabel>
            <strong style={{ display: "block", marginTop: "0.3rem" }}>
              {activeQuick ? QUICK_STATES.find((item) => item.key === activeQuick)?.label : "Подборка"}
            </strong>
            <p style={{ margin: "0.28rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8rem", lineHeight: 1.45 }}>
              Баллы показывают подтверждённую активность и не списываются при открытии возможности.
            </p>
          </div>
          <button type="button" onClick={openFilters}>Фильтры{category || status || sort !== "recommended" ? " •" : ""}</button>
        </div>
      </Card>

      <PointsRulesSheet />

      <BottomSheet open={showFilterSheet} onClose={() => setShowFilterSheet(false)} title="Фильтры">
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem", maxHeight: "68vh", overflowY: "auto" }}>
          <FilterGroup
            title="Категория"
            options={[{ value: null, label: "Все категории" }, ...categories.map((value) => ({ value, label: CATEGORY_LABELS[value] ?? value }))]}
            value={draftCategory}
            onChange={setDraftCategory}
          />
          <FilterGroup
            title="Статус"
            options={[
              { value: null, label: "Все" },
              { value: "available", label: "Доступно" },
              { value: "almost", label: "Скоро доступно" },
              { value: "closed", label: "Закрыто" },
            ]}
            value={draftStatus}
            onChange={(value) => setDraftStatus(value as OpportunityState | null)}
          />
          <FilterGroup
            title="Сортировка"
            options={(Object.keys(UI_SORT_LABELS) as UiSort[]).map((value) => ({ value, label: UI_SORT_LABELS[value] }))}
            value={draftSort}
            onChange={(value) => setDraftSort((value ?? "recommended") as UiSort)}
          />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.55rem", position: "sticky", bottom: 0, background: "var(--era-surface)", paddingTop: "0.35rem" }}>
            <button type="button" onClick={resetFilters}>Сбросить</button>
            <button type="button" className="era-btn-primary" onClick={applyFilters}>
              {previewCount === null ? "Показать" : `Показать ${previewCount}`}
            </button>
          </div>
        </div>
      </BottomSheet>

      {actionError && <p style={{ margin: 0, color: "var(--era-error)", fontSize: "0.82rem" }}>{actionError}</p>}
      {listState.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {listState.status === "error" && <EmptyState text="Не удалось загрузить возможности." />}
      {listState.status === "ready" && offers.length === 0 && <EmptyState text="По этим параметрам пока ничего нет." />}

      {offers.map((offer) => (
        <OpportunityCard
          key={offer.id}
          offer={offer}
          expanded={expandedId === offer.id}
          pending={pendingId === offer.id}
          onToggle={() => setExpandedId((current) => current === offer.id ? null : offer.id)}
          onApply={() => handleApply(offer.id)}
          onSave={() => handleSave(offer)}
        />
      ))}
    </div>
  );
}

function FilterGroup<T extends string>({ title, options, value, onChange }: {
  title: string;
  options: { value: T | null; label: string }[];
  value: T | null;
  onChange: (value: T | null) => void;
}) {
  return (
    <div>
      <strong style={{ display: "block", marginBottom: "0.45rem" }}>{title}</strong>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.45rem" }}>
        {options.map((option) => {
          const active = option.value === value;
          return (
            <button key={option.label} type="button" onClick={() => onChange(option.value)} style={{ padding: "0.48rem 0.7rem", borderRadius: "var(--era-radius-pill)", border: active ? "1px solid var(--era-violet)" : "1px solid var(--era-border)", background: active ? "var(--era-tint-violet)" : "var(--era-surface-2)", color: active ? "var(--era-violet)" : "var(--era-text)", fontWeight: 700, fontSize: "0.8rem" }}>
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function OpportunityCard({ offer, expanded, pending, onToggle, onApply, onSave }: {
  offer: Opportunity;
  expanded: boolean;
  pending: boolean;
  onToggle: () => void;
  onApply: () => void;
  onSave: () => void;
}) {
  const applied = APPLIED_STATUSES.has(offer.application_status ?? "");
  const pointsCheck = offer.eligibility_checks.find((check) => check.key === "points");
  const currentPoints = pointsCheck ? Number(pointsCheck.current) || 0 : 0;
  const progress = offer.required_points > 0 ? Math.min(100, Math.round((currentPoints / offer.required_points) * 100)) : 100;
  const remaining = Math.max(0, offer.required_points - currentPoints);

  return (
    <div id={`opportunity-${offer.id}`}>
      <Card>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "flex-start" }}>
            <div style={{ minWidth: 0 }}>
              <MonoLabel tone="violet">{offer.partner_name}</MonoLabel>
              <strong style={{ display: "block", marginTop: "0.3rem", lineHeight: 1.3 }}>{offer.title}</strong>
              <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8rem" }}>{CATEGORY_LABELS[offer.category ?? ""] ?? offer.category ?? "Возможность"}</p>
            </div>
            <StatusBadge label={offer.application_status ? APPLICATION_STATUS_LABELS[offer.application_status] ?? offer.application_status : STATE_LABELS[offer.state]} tone={offer.eligible ? "success" : "neutral"} />
          </div>

          {offer.required_points > 0 && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", color: "var(--era-text-muted)", fontSize: "0.78rem", marginBottom: "0.3rem" }}>
                <span>{formatPoints(currentPoints)} / {formatPoints(offer.required_points)}</span>
                <span>{progress}%</span>
              </div>
              <div style={{ height: 6, borderRadius: 999, overflow: "hidden", background: "var(--era-surface-2)" }}>
                <div style={{ width: `${progress}%`, height: "100%", background: "var(--era-gradient-signal)" }} />
              </div>
              {!offer.eligible && remaining > 0 && <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "0.78rem" }}>Ещё {formatPoints(remaining)} баллов до выполнения порога</p>}
            </div>
          )}

          <button type="button" onClick={onToggle} style={{ alignSelf: "flex-start" }}>{expanded ? "Скрыть" : "Подробнее"}</button>

          {expanded && (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
              <p style={{ margin: 0, color: "var(--era-text-secondary)", fontSize: "0.84rem", lineHeight: 1.5 }}>{offer.description}</p>
              {offer.missing_requirements.length > 0 && (
                <div style={{ padding: "0.75rem", borderRadius: "var(--era-radius-md)", background: "var(--era-surface-2)" }}>
                  <strong style={{ fontSize: "0.82rem" }}>Что ещё нужно</strong>
                  <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8rem" }}>{offer.missing_requirements.join(" · ")}</p>
                </div>
              )}
              {offer.reasons.length > 0 && <p style={{ margin: 0, color: "var(--era-violet)", fontSize: "0.8rem" }}>{offer.reasons.join(" · ")}</p>}
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                {!applied && (
                  <button type="button" className="era-btn-primary" disabled={pending || !offer.eligible} onClick={onApply}>
                    {offer.eligible ? "Подать заявку" : offer.state === "almost" ? "Скоро доступно" : "Условия не выполнены"}
                  </button>
                )}
                <button type="button" disabled={pending} onClick={onSave}>{offer.is_saved ? "Убрать из сохранённых" : "Сохранить"}</button>
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
  return (
    <div className="era-page" style={{ padding: "1.25rem 1.25rem var(--era-page-bottom-safe)", display: "flex", flexDirection: "column", gap: "1rem" }}>
      {onBack && <button type="button" onClick={onBack}>← Назад</button>}
      <div>
        <MonoLabel tone="violet">Рост открывает доступ</MonoLabel>
        <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "1.75rem", fontWeight: 800, margin: "0.35rem 0 0" }}>Возможности</h1>
        <p style={{ margin: "0.4rem 0 0", color: "var(--era-text-muted)", lineHeight: 1.45 }}>То, что становится доступно благодаря подтверждённой активности в ЭРА.</p>
      </div>
      {initialSection === "offers" && <OffersList initialItemId={initialItemId ?? null} />}
      {initialSection === "auctions" && <AuctionsPanel />}
      {initialSection === "rewards" && <RewardsPanel />}
      {initialSection === "surveys" && <SurveysPanel />}
    </div>
  );
}
