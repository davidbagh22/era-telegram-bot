import { useCallback, useState } from "react";
import { downloadDataExport, downloadResumePdf, fetchProfile, requestAccountDeletion } from "../api/client";
import { Avatar } from "../components/Avatar";
import { BottomSheet } from "../components/BottomSheet";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { EraScore } from "../components/EraScore";
import { PageHeader } from "../components/PageHeader";
import { PrimaryButton, SecondaryButton } from "../components/Buttons";
import { Skeleton, SkeletonCard } from "../components/Skeleton";
import { StatusBadge } from "../components/StatusBadge";
import { useToast } from "../components/Toast";
import { AwardIcon, ChevronRightIcon, EventIcon, ProjectsIcon, TaskIcon, WorkIcon } from "../components/icons";
import { useAsync } from "../hooks/useAsync";
import type { PortfolioEntry } from "../types/profile";
import { LeaderboardScreen } from "./LeaderboardScreen";

type PortfolioSection = "projects" | "events" | "tasks" | "volunteer" | "leadership" | "badges" | "certificates" | "recommendations";

const SECTIONS: { key: PortfolioSection; title: string }[] = [
  { key: "projects", title: "Проекты" },
  { key: "events", title: "События" },
  { key: "tasks", title: "Задания" },
  { key: "volunteer", title: "Социальный вклад" },
  { key: "leadership", title: "Лидерские роли" },
  { key: "badges", title: "Достижения" },
  { key: "certificates", title: "Сертификаты" },
  { key: "recommendations", title: "Рекомендации" },
];

interface ProfileScreenProps {
  isAdmin?: boolean;
  isLeader?: boolean;
  onEnterWorkspace?: () => void;
}

function entityRoute(entry: PortfolioEntry): string | null {
  if (!entry.entity_kind || !entry.entity_id) return null;
  if (entry.entity_kind === "project") return `#/projects/${entry.entity_id}`;
  if (entry.entity_kind === "event") return `#/events/${entry.entity_id}`;
  if (entry.entity_kind === "task") return `#/tasks/${entry.entity_id}`;
  return null;
}

export function ProfileScreen({ isAdmin, isLeader, onEnterWorkspace }: ProfileScreenProps = {}) {
  const state = useAsync(fetchProfile, []);
  const toast = useToast();
  const [section, setSection] = useState<PortfolioSection | null>(null);
  const [leaderboard, setLeaderboard] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [deletionOpen, setDeletionOpen] = useState(false);
  const [deletionBusy, setDeletionBusy] = useState(false);
  const [deletionRequested, setDeletionRequested] = useState(false);

  const downloadResume = useCallback(async () => {
    if (downloading) return;
    setDownloading(true);
    try {
      const blob = await downloadResumePdf();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "ERA_portfolio.pdf";
      link.click();
      URL.revokeObjectURL(url);
      toast.show("Портфолио готово", "success");
    } catch { toast.show("Не удалось скачать портфолио. Попробуйте ещё раз.", "error"); }
    finally { setDownloading(false); }
  }, [downloading, toast]);

  const exportData = useCallback(async () => {
    if (exporting) return;
    setExporting(true);
    try {
      const blob = await downloadDataExport();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "ERA_data_export.json";
      link.click();
      URL.revokeObjectURL(url);
      toast.show("Копия данных готова", "success");
    } catch { toast.show("Не удалось выгрузить данные. Попробуйте ещё раз.", "error"); }
    finally { setExporting(false); }
  }, [exporting, toast]);

  const requestDeletion = useCallback(async () => {
    if (deletionBusy || deletionRequested) return;
    setDeletionBusy(true);
    try {
      await requestAccountDeletion();
      setDeletionRequested(true);
      setDeletionOpen(false);
      toast.show("Заявка на удаление отправлена", "success");
    } catch { toast.show("Не удалось отправить заявку. Попробуйте ещё раз.", "error"); }
    finally { setDeletionBusy(false); }
  }, [deletionBusy, deletionRequested, toast]);

  if (leaderboard) return <LeaderboardScreen onBack={() => setLeaderboard(false)} />;
  if (state.status === "loading") return <div className="era-page era-page-shell"><div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}><Skeleton width={56} height={56} radius="50%" /><div style={{ flex: 1, display: "grid", gap: 6 }}><Skeleton height="1.1rem" width="60%" /><Skeleton height="0.75rem" width="38%" /></div></div><Skeleton height="9rem" radius="var(--era-radius-card)" /><SkeletonCard /><SkeletonCard /></div>;
  if (state.status === "error") return <div className="era-page era-page-shell"><EmptyState title="Профиль не загрузился" description="Ваши данные сохранены. Проверьте соединение и откройте профиль снова." /></div>;

  const data = state.data;
  const progress = data.growth.level_count <= 1 ? 100 : (data.growth.level_index / (data.growth.level_count - 1)) * 100;
  const score = data.stats.points ?? 0;
  const entries: Record<PortfolioSection, PortfolioEntry[]> = {
    projects: data.projects,
    events: data.events,
    tasks: data.tasks,
    volunteer: data.volunteer,
    leadership: data.leadership,
    badges: data.badges,
    certificates: data.certificates,
    recommendations: data.recommendations,
  };

  if (section) {
    const title = SECTIONS.find((item) => item.key === section)?.title ?? "Портфолио";
    return (
      <div className="era-page era-page-shell">
        <PageHeader title={title} eyebrow="Портфолио ЭРА" subtitle="Только реальные записи из вашего профиля." onBack={() => setSection(null)} />
        {entries[section].length === 0 ? <EmptyState title={`Пока нет записей: ${title.toLowerCase()}`} description="Раздел заполнится после подтверждённой активности." /> : <div style={{ display: "grid", gap: "0.75rem" }}>{entries[section].map((entry, index) => <PortfolioCard key={`${entry.title}-${entry.date_label}-${index}`} entry={entry} />)}</div>}
      </div>
    );
  }

  return (
    <div className="era-page era-page-shell">
      <PageHeader title="Профиль" eyebrow="Цифровое портфолио ЭРА" />

      <Card style={{ padding: "1.2rem" }}>
        <div style={{ display: "flex", gap: "0.9rem", alignItems: "center" }}>
          <Avatar firstName={data.first_name} lastName={data.last_name} />
          <div style={{ flex: 1, minWidth: 0 }}><h1 style={{ margin: 0, fontSize: "var(--era-text-2xl)", overflowWrap: "anywhere" }}>{data.full_name || data.first_name}</h1><p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)" }}>{data.growth.label}{data.city ? ` · ${data.city}` : ""}</p><p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>{data.period}</p></div>
        </div>
        {(data.directions.length > 0 || data.departments.length > 0) && <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginTop: "0.9rem" }}>{[...data.directions, ...data.departments].slice(0, 6).map((item) => <span key={item} style={{ padding: "0.35rem 0.55rem", borderRadius: 999, background: "var(--era-bg-subtle)", fontSize: "var(--era-text-xs)", fontWeight: 750 }}>{item}</span>)}</div>}
      </Card>

      <EraScore score={score} progressPercent={progress} levelLabel={data.growth.label} onClick={() => { window.location.hash = "#/progress"; }} />

      <section className="era-section">
        <h2 className="era-section-title">Статистика</h2>
        <div className="era-grid-2">
          <StatCard icon={<ProjectsIcon width={20} height={20} />} value={data.projects.length} label="Проекты" onClick={() => { window.location.hash = "#/projects"; }} />
          <StatCard icon={<EventIcon width={20} height={20} />} value={data.events.length} label="События" onClick={() => { window.location.hash = "#/events"; }} />
          <StatCard icon={<TaskIcon width={20} height={20} />} value={data.tasks.length} label="Задания" onClick={() => { window.location.hash = "#/tasks"; }} />
          <StatCard icon={<AwardIcon width={20} height={20} />} value={data.badges.length} label="Достижения" onClick={() => setSection("badges")} />
        </div>
      </section>

      {onEnterWorkspace && <Card interactive onClick={onEnterWorkspace} ariaLabel="Открыть управление ЭРА" style={{ borderColor: "rgba(227,38,54,.14)" }}><div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}><span style={{ width: 42, height: 42, borderRadius: 14, display: "grid", placeItems: "center", background: "var(--era-tint-red)", color: "var(--era-red)" }}><WorkIcon width={20} height={20} /></span><div style={{ flex: 1 }}><strong>Управление ЭРА</strong><p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>{isAdmin ? "Админ-панель: люди, события, проекты и аналитика" : isLeader ? "Пространство лидера" : "Рабочее пространство"}</p></div><ChevronRightIcon width={20} height={20} style={{ color: "var(--era-red)" }} /></div></Card>}

      <section className="era-section">
        <h2 className="era-section-title">Портфолио ЭРА</h2>
        <div style={{ display: "grid", gap: "0.55rem" }}>{SECTIONS.map((item) => <button key={item.key} type="button" onClick={() => setSection(item.key)} style={{ minHeight: 58, padding: "0.75rem 0.85rem", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", textAlign: "left", background: "var(--era-surface)" }}><span><strong>{item.title}</strong><span style={{ display: "block", marginTop: 2, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>{entries[item.key].length} записей</span></span><ChevronRightIcon width={19} height={19} /></button>)}</div>
      </section>

      {(data.skills.length > 0 || data.experience || data.occupation) && <section className="era-section"><h2 className="era-section-title">О вас</h2><Card>{data.occupation && <ProfileField label="Сейчас" value={data.occupation} />}{data.experience && <ProfileField label="Опыт" value={data.experience} />}{data.skills.length > 0 && <div style={{ marginTop: data.occupation || data.experience ? "0.9rem" : 0 }}><span className="era-kicker">Навыки</span><div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginTop: "0.45rem" }}>{data.skills.map((skill) => <StatusBadge key={skill} label={skill} tone="neutral" />)}</div></div>}</Card></section>}

      <SecondaryButton onClick={() => setLeaderboard(true)}>Рейтинг участников</SecondaryButton>
      <PrimaryButton busy={downloading} busyLabel="Формируем PDF…" onClick={() => void downloadResume()}>Скачать портфолио PDF</PrimaryButton>

      <section className="era-section">
        <h2 className="era-section-title">Данные и конфиденциальность</h2>
        <Card><p style={{ margin: 0, color: "var(--era-text-muted)" }}>Вы можете получить копию данных или отправить запрос на удаление аккаунта. Опасное действие всегда требует подтверждения.</p><SecondaryButton busy={exporting} busyLabel="Готовим файл…" onClick={() => void exportData()} style={{ width: "100%", marginTop: "0.75rem" }}>Скачать мои данные</SecondaryButton><button type="button" className="era-btn-danger" disabled={deletionRequested} onClick={() => setDeletionOpen(true)} style={{ width: "100%", marginTop: "0.5rem" }}>{deletionRequested ? "Заявка на удаление отправлена" : "Запросить удаление аккаунта"}</button></Card>
      </section>

      <BottomSheet open={deletionOpen} onClose={() => setDeletionOpen(false)} title="Запросить удаление аккаунта?">
        <p style={{ margin: 0, color: "var(--era-text-muted)" }}>Администратор получит заявку. До её выполнения данные останутся доступными вам в профиле.</p><div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", marginTop: "1rem" }}><SecondaryButton onClick={() => setDeletionOpen(false)}>Оставить</SecondaryButton><button type="button" className="era-btn-danger" disabled={deletionBusy} onClick={() => void requestDeletion()}>{deletionBusy ? "Отправляем…" : "Отправить заявку"}</button></div>
      </BottomSheet>
    </div>
  );
}

function StatCard({ icon, value, label, onClick }: { icon: React.ReactNode; value: number; label: string; onClick: () => void }) {
  return <Card interactive onClick={onClick} ariaLabel={`${label}: ${value}. Открыть список`} style={{ boxShadow: "none" }}><span style={{ color: "var(--era-red)" }}>{icon}</span><strong style={{ display: "block", marginTop: "0.55rem", fontSize: "1.75rem" }}>{value}</strong><span style={{ color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>{label}</span></Card>;
}

function PortfolioCard({ entry }: { entry: PortfolioEntry }) {
  const route = entityRoute(entry);
  const interactive = Boolean(route || entry.url);
  const action = interactive ? () => { if (route) window.location.hash = route; else if (entry.url) window.open(entry.url, "_blank", "noopener,noreferrer"); } : undefined;
  return <Card interactive={interactive} onClick={action} ariaLabel={interactive ? `${entry.title}. Открыть` : undefined}><div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}><div style={{ flex: 1, minWidth: 0 }}><strong style={{ overflowWrap: "anywhere" }}>{entry.title}</strong>{entry.description && <p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)" }}>{entry.description}</p>}<p style={{ margin: "0.45rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>{[entry.status, entry.date_label].filter(Boolean).join(" · ")}</p></div>{interactive && <ChevronRightIcon width={19} height={19} style={{ flexShrink: 0, color: "var(--era-text-muted)" }} />}</div></Card>;
}

function ProfileField({ label, value }: { label: string; value: string }) { return <div style={{ marginTop: "0.75rem" }}><span className="era-kicker">{label}</span><p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", whiteSpace: "pre-wrap" }}>{value}</p></div>; }
