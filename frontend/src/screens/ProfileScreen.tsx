import { useCallback, useState } from "react";
import { downloadDataExport, fetchProfile, requestAccountDeletion } from "../api/client";
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
      {entries.length === 0 ? <EmptyState text="Здесь пока нет записей." /> : (
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

interface ProfileScreenProps {
  isAdmin?: boolean;
  isLeader?: boolean;
  onEnterWorkspace?: () => void;
  onOpenDevelopment?: () => void;
}

export function ProfileScreen({ isAdmin, isLeader, onEnterWorkspace, onOpenDevelopment }: ProfileScreenProps = {}) {
  const state = useAsync(fetchProfile, []);
  const toast = useToast();
  const [showPortfolio, setShowPortfolio] = useState(false);
  const [showReferral, setShowReferral] = useState(false);
  const [activeCell, setActiveCell] = useState<DashboardCell | null>(null);
  const [exporting, setExporting] = useState(false);
  const [deletionOpen, setDeletionOpen] = useState(false);
  const [requestingDeletion, setRequestingDeletion] = useState(false);
  const [deletionRequested, setDeletionRequested] = useState(false);

  const handleExportData = useCallback(async () => {
    setExporting(true);
    try {
      const blob = await downloadDataExport();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "ERA_data_export.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      toast.show("Данные выгружены", "success");
    } catch {
      toast.show("Не удалось выгрузить данные.", "error");
    } finally {
      setExporting(false);
    }
  }, [toast]);

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

  if (showReferral) return <ReferralScreen onBack={() => setShowReferral(false)} />;
  if (showPortfolio) return <CareerPortfolioScreen onBack={() => setShowPortfolio(false)} />;

  if (state.status === "loading") {
    return (
      <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}><Skeleton width={48} height={48} radius="50%" /><Skeleton height="1.1rem" width="50%" /></div>
        <SkeletonCard /><SkeletonCard />
      </div>
    );
  }

  if (state.status === "error") return <StatusBanner title="Не удалось загрузить профиль" description="Откройте раздел ещё раз." />;

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

  if (activeCell) {
    const config = DASHBOARD_CELLS.find((item) => item.key === activeCell);
    return (
      <div className="era-page" style={{ padding: "1.25rem 1.25rem var(--era-page-bottom-safe)", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <button type="button" onClick={() => setActiveCell(null)} style={{ alignSelf: "flex-start" }}>← Назад</button>
        <PortfolioSection title={config?.title ?? "Результаты"} entries={resultEntries[activeCell]} />
      </div>
    );
  }

  return (
    <div className="era-page era-stagger" style={{ padding: "1.25rem 1.25rem var(--era-page-bottom-safe)", display: "flex", flexDirection: "column", gap: "1.15rem" }}>
      <Card gradient>
        <div style={{ display: "flex", gap: "0.9rem", alignItems: "center" }}>
          <Avatar firstName={data.first_name} lastName={data.last_name} size="lg" />
          <div style={{ minWidth: 0 }}>
            <MonoLabel tone="violet">Профиль</MonoLabel>
            <h1 style={{ margin: "0.25rem 0 0", fontFamily: "var(--era-font-display)", fontSize: "1.6rem", overflowWrap: "anywhere" }}>{data.full_name || data.first_name}</h1>
            <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-secondary)" }}>{data.growth.label}{data.city ? ` · ${data.city}` : ""}</p>
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: "0.6rem", marginTop: "1rem" }}>
          <div><strong style={{ display: "block", fontSize: "1.3rem" }}>{data.stats.points ?? 0}</strong><span style={{ color: "var(--era-text-muted)", fontSize: "0.72rem" }}>баллов</span></div>
          <div><strong style={{ display: "block", fontSize: "1.3rem" }}>{totalResults}</strong><span style={{ color: "var(--era-text-muted)", fontSize: "0.72rem" }}>результатов</span></div>
          <div><strong style={{ display: "block", fontSize: "1.3rem" }}>{data.growth.level_index + 1}</strong><span style={{ color: "var(--era-text-muted)", fontSize: "0.72rem" }}>уровень</span></div>
        </div>
      </Card>

      <section>
        <h2 style={{ margin: "0 0 0.7rem", fontSize: "var(--era-text-xl)" }}>Мой путь</h2>
        <ProgressBar currentIndex={data.growth.level_index} totalSteps={data.growth.level_count} labels={GROWTH_LABELS} />
      </section>

      <section>
        <h2 style={{ margin: "0 0 0.7rem", fontSize: "var(--era-text-xl)" }}>Мои результаты</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.6rem" }}>
          {DASHBOARD_CELLS.map((cell) => (
            <button key={cell.key} type="button" onClick={() => setActiveCell(cell.key)} style={{ textAlign: "left", padding: "0.85rem", borderRadius: "var(--era-radius-md)", background: "var(--era-surface)", border: "1px solid var(--era-border)" }}>
              <strong style={{ display: "block" }}>{cell.label}</strong>
              <span style={{ display: "block", marginTop: "0.22rem", color: "var(--era-text-muted)", fontSize: "0.78rem" }}>{resultEntries[cell.key].length} записей</span>
            </button>
          ))}
        </div>
      </section>

      <section style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
        <h2 style={{ margin: "0 0 0.15rem", fontSize: "var(--era-text-xl)" }}>Аккаунт</h2>
        <ActionCell title="Моё портфолио" description="Резюме, сертификаты и подтверждённые результаты" meta="Открыть" onClick={() => setShowPortfolio(true)} />
        {onOpenDevelopment && <ActionCell title="Мой вектор" description="Цели, состояние и история развития" meta="Открыть" onClick={onOpenDevelopment} />}
        <ActionCell title="Пригласить в ЭРА" description="Персональная ссылка · до +100 баллов за включившегося участника" meta="Открыть" onClick={() => setShowReferral(true)} />
        {(isAdmin || isLeader) && onEnterWorkspace && <ActionCell title={isAdmin ? "Управление ЭРА" : "Пространство лидера"} description="Рабочие инструменты и управление" meta="Открыть" onClick={onEnterWorkspace} />}
      </section>

      <section>
        <h2 style={{ margin: "0 0 0.7rem", fontSize: "var(--era-text-xl)" }}>Данные и конфиденциальность</h2>
        <Card>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
            <button type="button" disabled={exporting} onClick={handleExportData}>{exporting ? "Готовим файл…" : "Скачать мои данные (JSON)"}</button>
            <button type="button" disabled={deletionRequested} onClick={() => setDeletionOpen(true)} style={{ color: "var(--era-error)" }}>{deletionRequested ? "Заявка на удаление отправлена" : "Запросить удаление аккаунта"}</button>
          </div>
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
