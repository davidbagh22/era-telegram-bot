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
import { SignalOrb } from "../components/SignalOrb";
import { StatusBanner } from "../components/StatusBanner";
import { useToast } from "../components/Toast";
import { useAsync } from "../hooks/useAsync";
import { CareerPortfolioScreen } from "./CareerPortfolioScreen";
import { LeaderboardScreen } from "./LeaderboardScreen";
import { ReferralScreen } from "./ReferralScreen";
import type { PortfolioEntry } from "../types/profile";

const GROWTH_LABELS = ["Участник", "Активный", "Лидер"];

type ResultSection =
  | "projects"
  | "events"
  | "tasks"
  | "volunteer"
  | "leadership"
  | "badges"
  | "certificates"
  | "recommendations";

const RESULT_SECTIONS: { key: ResultSection; title: string; description: string }[] = [
  { key: "projects", title: "Проекты", description: "Проекты и роли, которые вы прошли в ЭРА" },
  { key: "events", title: "Мероприятия", description: "События, в которых вы участвовали" },
  { key: "tasks", title: "Задачи", description: "Практическая работа и выполненные результаты" },
  { key: "volunteer", title: "Волонтёрство", description: "Социальный вклад и инициативы" },
  { key: "leadership", title: "Лидерство", description: "Управленческий опыт и ответственность" },
  { key: "badges", title: "Достижения", description: "Знаки, уровни и признание вашего вклада" },
  { key: "certificates", title: "Сертификаты", description: "Подтверждения участия и обучения" },
  { key: "recommendations", title: "Рекомендации", description: "Рекомендательные материалы и признание" },
];

function PortfolioSection({ title, entries }: { title: string; entries: PortfolioEntry[] }) {
  return (
    <section>
      <h2 style={{ fontSize: "var(--era-text-xl)", margin: "0 0 0.75rem" }}>{title}</h2>
      {entries.length === 0 ? (
        <EmptyState text="Здесь пока нет записей." />
      ) : (
        <div className="era-stagger" style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {entries.map((entry, index) => (
            <Card key={`${entry.title}-${index}`}>
              <strong>{entry.title}</strong>
              {entry.description && (
                <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>{entry.description}</p>
              )}
              {(entry.status || entry.date_label) && (
                <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
                  {[entry.status, entry.date_label].filter(Boolean).join(" · ")}
                </p>
              )}
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
  const [exporting, setExporting] = useState(false);
  const [deletionOpen, setDeletionOpen] = useState(false);
  const [requestingDeletion, setRequestingDeletion] = useState(false);
  const [deletionRequested, setDeletionRequested] = useState(false);
  const [showLeaderboard, setShowLeaderboard] = useState(false);
  const [showCareerPortfolio, setShowCareerPortfolio] = useState(false);
  const [showReferral, setShowReferral] = useState(false);
  const [resultSection, setResultSection] = useState<ResultSection | null>(null);
  const toast = useToast();

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
      toast.show("Не удалось выгрузить данные. Попробуйте ещё раз.", "error");
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
      toast.show("Заявка на удаление аккаунта отправлена администратору", "success");
    } catch {
      toast.show("Не удалось отправить заявку. Попробуйте ещё раз.", "error");
    } finally {
      setRequestingDeletion(false);
    }
  }, [toast]);

  if (showReferral) return <ReferralScreen onBack={() => setShowReferral(false)} />;
  if (showCareerPortfolio) return <CareerPortfolioScreen onBack={() => setShowCareerPortfolio(false)} />;
  if (showLeaderboard) return <LeaderboardScreen onBack={() => setShowLeaderboard(false)} />;

  if (state.status === "loading") {
    return (
      <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <Skeleton width={48} height={48} radius="50%" />
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "0.375rem" }}>
            <Skeleton height="1.125rem" width="55%" />
            <Skeleton height="0.75rem" width="35%" />
          </div>
        </div>
        <Skeleton height="2.5rem" radius="var(--era-radius-control)" />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (state.status === "error") {
    return <StatusBanner title="Не удалось загрузить профиль" description="Потяните вниз, чтобы обновить страницу, или откройте ЭРА заново." />;
  }

  const { data } = state;
  const resultEntries: Record<ResultSection, PortfolioEntry[]> = {
    projects: data.projects,
    events: data.events,
    tasks: data.tasks,
    volunteer: data.volunteer,
    leadership: data.leadership,
    badges: data.badges,
    certificates: data.certificates,
    recommendations: data.recommendations,
  };

  if (resultSection) {
    const config = RESULT_SECTIONS.find((item) => item.key === resultSection);
    return (
      <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <button type="button" onClick={() => setResultSection(null)} style={{ alignSelf: "flex-start" }}>← Назад</button>
        <PortfolioSection title={config?.title ?? "Результаты"} entries={resultEntries[resultSection]} />
      </div>
    );
  }

  const points = data.stats.points ?? 0;
  const totalResults = Object.values(resultEntries).reduce((total, entries) => total + entries.length, 0);
  const orbitPercent = data.growth.level_count <= 1
    ? 1
    : Math.max(0, Math.min(1, data.growth.level_index / (data.growth.level_count - 1)));

  return (
    <div className="era-page era-stagger" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem", minWidth: 0 }}>
      <Card gradient style={{ position: "relative", overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem", minWidth: 0 }}>
          <Avatar firstName={data.first_name} lastName={data.last_name} size="lg" />
          <div style={{ minWidth: 0 }}>
            <MonoLabel tone="violet">Мой путь в ЭРА</MonoLabel>
            <h1
              style={{
                fontFamily: "var(--era-font-display)",
                fontSize: "var(--era-text-3xl)",
                fontWeight: 800,
                margin: "0.25rem 0 0",
                letterSpacing: "-0.02em",
                textTransform: "uppercase",
                overflowWrap: "anywhere",
              }}
            >
              {data.full_name || data.first_name}
            </h1>
            <p style={{ margin: "0.3rem 0 0", color: "var(--era-text-secondary)" }}>
              {data.growth.label}{data.city ? ` · ${data.city}` : ""}
            </p>
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "center", padding: "1.5rem 0 0.5rem" }}>
          <SignalOrb percent={orbitPercent} size={168} animationKey="profile-signal-orb">
            <div>
              <strong style={{ display: "block", fontFamily: "var(--era-font-display)", fontSize: "2.1rem", fontWeight: 900, lineHeight: 1 }}>{points}</strong>
              <MonoLabel>баллов</MonoLabel>
            </div>
          </SignalOrb>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.75rem", marginTop: "0.5rem" }}>
          <div style={{ textAlign: "center" }}><strong style={{ fontFamily: "var(--era-font-display)", fontSize: "var(--era-text-2xl)", fontWeight: 800 }}>{Math.round(orbitPercent * 100)}%</strong><span style={{ display: "block", color: "var(--era-text-secondary)", fontSize: "var(--era-text-xs)" }}>до следующего ранга</span></div>
          <div style={{ textAlign: "center" }}><strong style={{ fontFamily: "var(--era-font-display)", fontSize: "var(--era-text-2xl)", fontWeight: 800 }}>{totalResults}</strong><span style={{ display: "block", color: "var(--era-text-secondary)", fontSize: "var(--era-text-xs)" }}>результатов</span></div>
        </div>
      </Card>

      <section>
        <h2 style={{ margin: "0 0 0.75rem", fontSize: "var(--era-text-xl)" }}>Рост</h2>
        <ProgressBar currentIndex={data.growth.level_index} totalSteps={data.growth.level_count} labels={GROWTH_LABELS} />
        <Card style={{ marginTop: "0.75rem" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {GROWTH_LABELS.map((label, index) => {
              const reached = index <= data.growth.level_index;
              const current = index === data.growth.level_index;
              return (
                <div key={label} style={{ display: "grid", gridTemplateColumns: "1.25rem 1fr", gap: "0.75rem", alignItems: "start" }}>
                  <span aria-hidden="true" style={{ width: 12, height: 12, marginTop: 3, borderRadius: "50%", background: reached ? "var(--era-red)" : "var(--era-ring-track)", boxShadow: current ? "0 0 0 5px var(--era-tint-red)" : "none" }} />
                  <div>
                    <strong style={{ color: reached ? "var(--era-text)" : "var(--era-text-muted)" }}>{label}</strong>
                    {current && <span style={{ display: "block", marginTop: "0.15rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>Вы здесь сейчас</span>}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      </section>

      <section>
        <h2 style={{ margin: "0 0 0.75rem", fontSize: "var(--era-text-xl)" }}>Профессиональный рост</h2>
        <ActionCell
          title="Моё портфолио"
          description="Резюме, достижения, сертификаты, подтверждающие файлы и рекомендация ЭРА"
          meta="Открыть"
          onClick={() => setShowCareerPortfolio(true)}
        />
      </section>

      {onOpenDevelopment && (
        <section>
          <h2 style={{ margin: "0 0 0.75rem", fontSize: "var(--era-text-xl)" }}>Развитие</h2>
          <ActionCell
            title="Мой вектор"
            description="Моё состояние, личная история, исследования и цели"
            meta="Ты ↔ ты"
            onClick={onOpenDevelopment}
          />
        </section>
      )}

      <section>
        <h2 style={{ margin: "0 0 0.75rem", fontSize: "var(--era-text-xl)" }}>Сообщество</h2>
        <ActionCell
          title="Пригласить друга"
          description="Ваш личный код и ссылка. +200 каждому после регистрации и общего чата, ещё +500 после первого подтверждённого мероприятия"
          meta="Открыть"
          onClick={() => setShowReferral(true)}
        />
      </section>

      {onEnterWorkspace && (
        <ActionCell
          title="Управление ЭРА"
          description={isAdmin ? "Открыть режим администратора" : isLeader ? "Открыть пространство лидера" : "Открыть рабочее пространство"}
          onClick={onEnterWorkspace}
        />
      )}

      <ActionCell title="Рейтинг участников" description="Ваше место, баллы и активные участники" onClick={() => setShowLeaderboard(true)} />

      <section>
        <h2 style={{ margin: "0 0 0.75rem", fontSize: "var(--era-text-xl)" }}>Мои результаты</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", minWidth: 0 }}>
          {RESULT_SECTIONS.map((item) => (
            <ActionCell
              key={item.key}
              title={item.title}
              description={item.description}
              meta={`${resultEntries[item.key].length} записей`}
              onClick={() => setResultSection(item.key)}
            />
          ))}
        </div>
      </section>

      {(data.departments.length > 0 || data.directions.length > 0) && (
        <Card>
          {data.departments.length > 0 && <p style={{ margin: 0 }}>Отделы: {data.departments.join(", ")}</p>}
          {data.directions.length > 0 && <p style={{ margin: data.departments.length > 0 ? "0.25rem 0 0" : 0 }}>Направления: {data.directions.join(", ")}</p>}
        </Card>
      )}

      <section>
        <h2 style={{ fontSize: "var(--era-text-xl)", margin: "0 0 0.75rem" }}>Данные и конфиденциальность</h2>
        <Card>
          <p style={{ margin: "0 0 0.75rem", color: "var(--era-text-muted)" }}>
            Скачайте копию данных, которые ЭРА хранит о вас, или запросите удаление аккаунта.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <button type="button" disabled={exporting} onClick={handleExportData}>{exporting ? "Готовим файл…" : "Скачать мои данные (JSON)"}</button>
            <button type="button" disabled={deletionRequested} onClick={() => setDeletionOpen(true)} style={{ color: "var(--era-error)" }}>
              {deletionRequested ? "Заявка на удаление отправлена" : "Запросить удаление аккаунта"}
            </button>
          </div>
        </Card>
      </section>

      <BottomSheet open={deletionOpen} onClose={() => setDeletionOpen(false)} title="Запросить удаление аккаунта?">
        <p style={{ color: "var(--era-text-muted)", margin: "0 0 1rem" }}>
          Заявку рассмотрит администратор. После подтверждения ваши личные данные будут обезличены, а аккаунт — архивирован. Это действие нельзя отменить самостоятельно.
        </p>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button type="button" onClick={() => setDeletionOpen(false)} style={{ flex: 1 }}>Отмена</button>
          <button type="button" className="era-btn-primary" disabled={requestingDeletion} onClick={handleRequestDeletion} style={{ flex: 1 }}>
            {requestingDeletion ? "Отправляем…" : "Отправить заявку"}
          </button>
        </div>
      </BottomSheet>
    </div>
  );
}
