import { useCallback, useState } from "react";
import { fetchMe, fetchProfile, requestAccountDeletion } from "../api/client";
import { ActionCell } from "../components/ActionCell";
import { Avatar } from "../components/Avatar";
import { BottomSheet } from "../components/BottomSheet";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { MonoLabel } from "../components/MonoLabel";
import { ProgressBar } from "../components/ProgressBar";
import { Skeleton, SkeletonCard } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import { useToast } from "../components/Toast";
import { useAsync } from "../hooks/useAsync";
import { CareerPortfolioScreen } from "./CareerPortfolioScreen";
import { ReferralScreen } from "./ReferralScreen";
import type { PortfolioEntry } from "../types/profile";

const GROWTH_LABELS = ["Участник", "Активный", "Лидер"];
type DashboardCell = "projects" | "events" | "tasks" | "volunteer" | "leadership" | "achievements";

const DASHBOARD_CELLS: { key: DashboardCell; label: string; title: string }[] = [
  { key: "projects", label: "Проекты", title: "Проекты" },
  { key: "events", label: "События", title: "События" },
  { key: "tasks", label: "Задачи", title: "Задачи" },
  { key: "volunteer", label: "Волонтёрство", title: "Волонтёрство" },
  { key: "leadership", label: "Лидерство", title: "Лидерство" },
  { key: "achievements", label: "Достижения", title: "Достижения" },
];

function PortfolioSection({ title, entries }: { title: string; entries: PortfolioEntry[] }) {
  return (
    <section>
      <h2 style={{ margin: "0 0 0.75rem", fontSize: "var(--era-text-xl)" }}>{title}</h2>
      {entries.length === 0 ? <EmptyState text="Здесь пока нет подтверждённых записей." /> : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
          {entries.map((entry, index) => (
            <Card key={`${entry.title}-${index}`}>
              <strong>{entry.title}</strong>
              {entry.description && <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>{entry.description}</p>}
              {(entry.status || entry.date_label) && <p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>{[entry.status, entry.date_label].filter(Boolean).join(" · ")}</p>}
            </Card>
          ))}
        </div>
      )}
    </section>
  );
}

function dateOrder(value: string): number {
  const [day, month, year] = value.split(".").map(Number);
  if (!day || !month || !year) return 0;
  return new Date(year, month - 1, day).getTime();
}

interface ProfileScreenProps {
  isAdmin?: boolean;
  isLeader?: boolean;
  onEnterWorkspace?: () => void;
  onOpenDevelopment?: () => void;
}

export function ProfileScreen({ isAdmin, isLeader, onEnterWorkspace, onOpenDevelopment }: ProfileScreenProps = {}) {
  const state = useAsync(fetchProfile, []);
  const me = useAsync(fetchMe, []);
  const toast = useToast();
  const [showPortfolio, setShowPortfolio] = useState(false);
  const [showReferral, setShowReferral] = useState(false);
  const [activeCell, setActiveCell] = useState<DashboardCell | null>(null);
  const [deletionOpen, setDeletionOpen] = useState(false);
  const [requestingDeletion, setRequestingDeletion] = useState(false);
  const [deletionRequested, setDeletionRequested] = useState(false);

  const referralsEnabled = me.status === "ready" && me.data.features.referrals;
  const vectorEnabled = me.status === "ready" && me.data.features.vector;

  const handleRequestDeletion = useCallback(async () => {
    setRequestingDeletion(true);
    try {
      await requestAccountDeletion();
      setDeletionRequested(true);
      setDeletionOpen(false);
      toast.show("Заявка на удаление отправлена", "success");
    } catch {
      toast.show("Не удалось отправить заявку.", "error");
    } finally {
      setRequestingDeletion(false);
    }
  }, [toast]);

  if (showReferral && referralsEnabled) return <ReferralScreen onBack={() => setShowReferral(false)} />;
  if (showPortfolio) return <CareerPortfolioScreen onBack={() => setShowPortfolio(false)} />;

  if (state.status === "loading" || me.status === "loading") {
    return (
      <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}><Skeleton width={48} height={48} radius="50%" /><Skeleton height="1.1rem" width="50%" /></div>
        <SkeletonCard /><SkeletonCard />
      </div>
    );
  }

  if (state.status === "error") return <StatusBanner title="Не удалось загрузить профиль" description="Открой раздел ещё раз." />;

  const { data } = state;
  const resultEntries = {
    projects: data.projects,
    events: data.events,
    tasks: data.tasks,
    volunteer: data.volunteer,
    leadership: data.leadership,
    achievements: [...data.badges, ...data.certificates, ...data.recommendations],
  } satisfies Record<DashboardCell, PortfolioEntry[]>;
  const totalResults = Object.values(resultEntries).reduce((sum, entries) => sum + entries.length, 0);
  const timeline = Object.entries(resultEntries)
    .flatMap(([group, entries]) => entries.map((entry) => ({ ...entry, group })))
    .filter((entry) => Boolean(entry.date_label))
    .sort((a, b) => dateOrder(b.date_label) - dateOrder(a.date_label))
    .slice(0, 8);

  if (activeCell) {
    const config = DASHBOARD_CELLS.find((item) => item.key === activeCell);
    return (
      <div className="era-page" style={{ padding: "1.25rem 1rem var(--era-page-bottom-safe)", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <button type="button" onClick={() => setActiveCell(null)} style={{ alignSelf: "flex-start", minHeight: 44 }}>← Назад</button>
        <PortfolioSection title={config?.title ?? "Результаты"} entries={resultEntries[activeCell]} />
      </div>
    );
  }

  return (
    <div className="era-page era-stagger" style={{ padding: "1.25rem 1rem var(--era-page-bottom-safe)", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <Card gradient>
        <div style={{ display: "flex", gap: "0.9rem", alignItems: "center" }}>
          <Avatar firstName={data.first_name} lastName={data.last_name} size="lg" />
          <div style={{ minWidth: 0 }}>
            <MonoLabel tone="violet">Профиль</MonoLabel>
            <h1 style={{ margin: "0.25rem 0 0", fontFamily: "var(--era-font-display)", fontSize: "1.75rem", overflowWrap: "anywhere" }}>{data.full_name || data.first_name}</h1>
            <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-secondary)" }}>{data.growth.label}{data.city ? ` · ${data.city}` : ""}</p>
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: "0.6rem", marginTop: "1rem" }}>
          <div><strong style={{ display: "block", fontSize: "1.3rem" }}>{data.stats.points ?? 0}</strong><span style={{ color: "var(--era-text-muted)", fontSize: "0.75rem" }}>баллов</span></div>
          <div><strong style={{ display: "block", fontSize: "1.3rem" }}>{totalResults}</strong><span style={{ color: "var(--era-text-muted)", fontSize: "0.75rem" }}>результатов</span></div>
          <div><strong style={{ display: "block", fontSize: "1.3rem" }}>{data.growth.level_index + 1}</strong><span style={{ color: "var(--era-text-muted)", fontSize: "0.75rem" }}>этап пути</span></div>
        </div>
      </Card>

      <section>
        <h2 style={{ margin: "0 0 0.7rem", fontSize: "var(--era-text-xl)" }}>Мой путь</h2>
        <ProgressBar currentIndex={data.growth.level_index} totalSteps={data.growth.level_count} labels={GROWTH_LABELS} />
        {data.growth_criteria.next_label && data.growth_criteria.criteria.length > 0 && (
          <Card style={{ marginTop: "0.75rem" }}>
            <strong>До уровня «{data.growth_criteria.next_label}»</strong>
            <p style={{ margin: "0.3rem 0 0.7rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
              Достаточно выполнить любой из подтверждённых вариантов. Баллы сами по себе уровень не меняют.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {data.growth_criteria.criteria.map((criterion) => (
                <div key={criterion.key} style={{ display: "grid", gridTemplateColumns: "1.4rem 1fr auto", gap: "0.5rem", alignItems: "start" }}>
                  <span aria-hidden="true" style={{ color: criterion.done ? "var(--era-success)" : "var(--era-text-muted)", fontWeight: 800 }}>{criterion.done ? "✓" : "○"}</span>
                  <span style={{ lineHeight: 1.4 }}>{criterion.label}</span>
                  <span style={{ color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)", whiteSpace: "nowrap" }}>{criterion.current}/{criterion.required}</span>
                </div>
              ))}
            </div>
          </Card>
        )}
      </section>

      <section>
        <h2 style={{ margin: "0 0 0.7rem", fontSize: "var(--era-text-xl)" }}>Мой вклад и опыт</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.6rem" }}>
          {DASHBOARD_CELLS.map((cell) => (
            <button key={cell.key} type="button" onClick={() => setActiveCell(cell.key)} style={{ minHeight: 72, textAlign: "left", padding: "0.85rem", borderRadius: "var(--era-radius-md)", background: "var(--era-surface)", border: "1px solid var(--era-border)" }}>
              <strong style={{ display: "block" }}>{cell.label}</strong>
              <span style={{ display: "block", marginTop: "0.22rem", color: "var(--era-text-muted)", fontSize: "0.78rem" }}>{resultEntries[cell.key].length} записей</span>
            </button>
          ))}
        </div>
      </section>

      <section>
        <h2 style={{ margin: "0 0 0.7rem", fontSize: "var(--era-text-xl)" }}>Лента пути</h2>
        {timeline.length === 0 ? <EmptyState text="История появится после первых подтверждённых действий." /> : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0" }}>
            {timeline.map((entry, index) => (
              <div key={`${entry.group}-${entry.title}-${entry.date_label}-${index}`} style={{ display: "grid", gridTemplateColumns: "1.25rem 1fr", gap: "0.65rem", minWidth: 0 }}>
                <div style={{ position: "relative", display: "flex", justifyContent: "center" }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", marginTop: "0.45rem", background: "var(--era-violet)", zIndex: 1 }} />
                  {index < timeline.length - 1 && <span style={{ position: "absolute", top: "0.9rem", bottom: "-0.15rem", width: 1, background: "var(--era-border)" }} />}
                </div>
                <div style={{ paddingBottom: "0.9rem", minWidth: 0 }}>
                  <span style={{ color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>{entry.date_label}</span>
                  <strong style={{ display: "block", marginTop: "0.15rem", overflowWrap: "anywhere" }}>{entry.title}</strong>
                  {entry.status && <span style={{ display: "block", marginTop: "0.15rem", color: "var(--era-text-secondary)", fontSize: "var(--era-text-sm)" }}>{entry.status}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
        <h2 style={{ margin: "0 0 0.15rem", fontSize: "var(--era-text-xl)" }}>Ещё</h2>
        <ActionCell title="Моё портфолио" description="Резюме, сертификаты и подтверждённые результаты" meta="Открыть" onClick={() => setShowPortfolio(true)} />
        {vectorEnabled && onOpenDevelopment && <ActionCell title="Мой вектор" description="Личные цели, состояние и история развития" meta="Открыть" onClick={onOpenDevelopment} />}
        {referralsEnabled && <ActionCell title="Пригласить в ЭРА" description="Персональная ссылка и история приглашений" meta="Открыть" onClick={() => setShowReferral(true)} />}
        {(isAdmin || isLeader) && onEnterWorkspace && <ActionCell title={isAdmin ? "Управление ЭРА" : "Пространство лидера"} description="Рабочие инструменты и управление" meta="Открыть" onClick={onEnterWorkspace} />}
      </section>

      <section>
        <h2 style={{ margin: "0 0 0.7rem", fontSize: "var(--era-text-xl)" }}>Данные и конфиденциальность</h2>
        <Card>
          <button type="button" disabled={deletionRequested} onClick={() => setDeletionOpen(true)} style={{ color: "var(--era-error)", minHeight: 44, textAlign: "left" }}>
            {deletionRequested ? "Заявка на удаление отправлена" : "Запросить удаление аккаунта"}
          </button>
        </Card>
      </section>

      <BottomSheet open={deletionOpen} onClose={() => setDeletionOpen(false)} title="Запросить удаление аккаунта?">
        <p style={{ margin: "0 0 1rem", color: "var(--era-text-muted)" }}>После проверки личные данные будут обезличены, а аккаунт архивирован.</p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
          <button type="button" onClick={() => setDeletionOpen(false)}>Отмена</button>
          <button type="button" className="era-btn-primary" disabled={requestingDeletion} onClick={handleRequestDeletion}>{requestingDeletion ? "Отправляем…" : "Отправить"}</button>
        </div>
      </BottomSheet>
    </div>
  );
}
