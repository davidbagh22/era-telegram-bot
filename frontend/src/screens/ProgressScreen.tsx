import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ProgressRing } from "../components/ProgressRing";
import { Skeleton, SkeletonCard } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import { useHome } from "../hooks/useHome";

interface ProgressScreenProps {
  onBack: () => void;
  onOpenProjects?: () => void;
  onOpenTasks?: () => void;
  onOpenEvents?: () => void;
}

export function ProgressScreen({ onBack, onOpenProjects, onOpenTasks, onOpenEvents }: ProgressScreenProps) {
  const home = useHome();

  if (home.status === "loading") {
    return <div className="era-page" style={{ padding: "1.15rem", display: "flex", flexDirection: "column", gap: "1rem" }}><Skeleton height="3rem" width="48%" /><Skeleton height="12rem" radius="var(--era-radius-card)" /><SkeletonCard /></div>;
  }
  if (home.status === "error") return <StatusBanner title="Не получилось загрузить прогресс" description="Ваши данные не изменены. Вернитесь назад и попробуйте ещё раз." />;

  const { data } = home;
  const percent = data.growth.level_count <= 1 ? 1 : data.growth.level_index / (data.growth.level_count - 1);
  const signals = [
    { label: "Проекты", value: data.activity.projects, onClick: onOpenProjects },
    { label: "Выполненные задания", value: data.activity.completed_tasks, onClick: onOpenTasks },
    { label: "Портфолио", value: data.activity.portfolio_items },
  ];

  return (
    <div className="era-page" style={{ padding: "1.15rem 1.15rem 1.5rem", display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <header style={{ display: "flex", alignItems: "center", gap: ".75rem" }}>
        <button type="button" onClick={onBack} aria-label="Назад" style={{ width: 44, minWidth: 44, height: 44, padding: 0 }}>←</button>
        <div><h1 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>Мой прогресс</h1><p style={{ margin: ".2rem 0 0", color: "var(--era-text-muted)" }}>Каждая цифра объясняется реальной активностью.</p></div>
      </header>

      <Card gradient style={{ padding: "1.25rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "1rem" }}>
          <div><span style={{ color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, letterSpacing: ".08em" }}>ERA SCORE</span><strong style={{ display: "block", marginTop: ".15rem", fontSize: "3.25rem", lineHeight: 1 }}>{data.points_balance}</strong><p style={{ margin: ".55rem 0 0", color: "var(--era-text-muted)" }}>Текущий статус: {data.growth.label}</p></div>
          <div style={{ position: "relative", width: 108, height: 108 }}><ProgressRing percent={percent} size={108} /><div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", textAlign: "center" }}><div><strong style={{ display: "block", fontSize: "1.2rem" }}>{Math.round(percent * 100)}%</strong><span style={{ fontSize: ".68rem", color: "var(--era-text-muted)" }}>путь уровня</span></div></div></div>
        </div>
      </Card>

      <section style={{ display: "flex", flexDirection: "column", gap: ".7rem" }}>
        <h2 style={{ margin: 0, fontSize: "var(--era-text-xl)" }}>Из чего складывается рост</h2>
        {signals.map((signal) => <Card key={signal.label} onClick={signal.onClick} style={{ boxShadow: "none" }}><div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "center" }}><span>{signal.label}</span><strong style={{ color: "var(--era-red)", fontSize: "1.25rem" }}>{signal.value}</strong></div></Card>)}
      </section>

      <section style={{ display: "flex", flexDirection: "column", gap: ".7rem" }}>
        <h2 style={{ margin: 0, fontSize: "var(--era-text-xl)" }}>Что делать дальше</h2>
        {data.next_step ? <Card style={{ borderLeft: "3px solid var(--era-red)" }}><strong>{data.next_step.title}</strong><p style={{ margin: ".35rem 0 0", color: "var(--era-text-muted)" }}>{data.next_step.description}</p></Card> : <EmptyState text="Следующий персональный шаг пока не сформирован. Выберите проект, задание или событие." />}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: ".65rem" }}>
          {onOpenProjects && <button type="button" className="era-btn-primary" onClick={onOpenProjects}>Проекты</button>}
          {onOpenEvents && <button type="button" onClick={onOpenEvents}>События</button>}
        </div>
      </section>
    </div>
  );
}
