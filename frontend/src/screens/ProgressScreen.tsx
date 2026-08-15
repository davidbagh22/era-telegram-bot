import { fetchHistory, fetchHome, fetchProfile } from "../api/client";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { EraScore } from "../components/EraScore";
import { PageHeader } from "../components/PageHeader";
import { SkeletonCard } from "../components/Skeleton";
import { useAsync } from "../hooks/useAsync";

export function ProgressScreen() {
  const home = useAsync(fetchHome, []);
  const profile = useAsync(fetchProfile, []);
  const history = useAsync(fetchHistory, []);

  const goBack = () => {
    if (window.history.length > 1) window.history.back();
    else window.location.hash = "#/home";
  };

  if (home.status === "loading" || profile.status === "loading") {
    return <div className="era-page era-page-shell"><PageHeader title="Мой прогресс" onBack={goBack} /><SkeletonCard /><SkeletonCard /></div>;
  }
  if (home.status === "error" || profile.status === "error") {
    return <div className="era-page era-page-shell"><PageHeader title="Мой прогресс" onBack={goBack} /><EmptyState title="Прогресс пока не загрузился" description="Ваши баллы и результаты сохранены. Попробуйте открыть экран снова." /></div>;
  }

  const score = home.data.points_balance;
  const growth = home.data.growth;
  const progressPercent = growth.level_count <= 1 ? 100 : (growth.level_index / (growth.level_count - 1)) * 100;
  const pointsHistory = history.status === "ready" ? history.data.filter((item) => item.kind === "points").slice(0, 12) : [];
  const nextLevel = growth.level_index < growth.level_count - 1 ? ["Участник", "Активный", "Лидер"][growth.level_index + 1] : null;

  return (
    <div className="era-page era-page-shell">
      <PageHeader title="Мой прогресс" eyebrow="Рост в ЭРА" subtitle="Здесь нет скрытых цифр: Score складывается из подтверждённых действий и начислений." onBack={goBack} />
      <EraScore score={score} progressPercent={progressPercent} levelLabel={growth.label} />

      <section className="era-section">
        <h2 className="era-section-title">Из чего складывается путь</h2>
        <div className="era-grid-2">
          <ProgressMetric value={profile.data.projects.length} label="проекты" />
          <ProgressMetric value={profile.data.events.length} label="события" />
          <ProgressMetric value={profile.data.tasks.length} label="задания" />
          <ProgressMetric value={profile.data.badges.length} label="достижения" />
        </div>
      </section>

      <Card>
        <p className="era-kicker">Текущий статус</p>
        <strong style={{ display: "block", marginTop: "0.35rem", fontSize: "var(--era-text-2xl)" }}>{growth.label}</strong>
        <p style={{ margin: "0.45rem 0 0", color: "var(--era-text-muted)" }}>
          {nextLevel
            ? `Следующая ступень — ${nextLevel}. Система показывает фактическую позицию в маршруте Участник → Активный → Лидер и не придумывает искусственный порог баллов.`
            : "Вы на верхней ступени текущего маршрута. Дальше важны качество результатов и ответственность в реальных проектах."}
        </p>
      </Card>

      <section className="era-section">
        <h2 className="era-section-title">Последние начисления</h2>
        {history.status === "loading" && <SkeletonCard />}
        {history.status === "error" && <EmptyState title="История не загрузилась" description="Текущий Score виден выше; детализацию начислений попробуйте открыть позже." />}
        {history.status === "ready" && pointsHistory.length === 0 && <EmptyState title="Начислений пока нет" description="Баллы появятся после подтверждённых действий в ЭРА." />}
        {pointsHistory.map((entry, index) => (
          <Card key={`${entry.title}-${entry.date}-${index}`} style={{ boxShadow: "none" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem" }}>
              <div><strong>{entry.title}</strong><p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>{entry.detail}</p></div>
              <span style={{ color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", whiteSpace: "nowrap" }}>{entry.date}</span>
            </div>
          </Card>
        ))}
      </section>
    </div>
  );
}

function ProgressMetric({ value, label }: { value: number; label: string }) {
  return <Card style={{ boxShadow: "none" }}><strong className="era-number" style={{ fontSize: "1.75rem" }}>{value}</strong><span style={{ display: "block", marginTop: 5, color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>{label}</span></Card>;
}
