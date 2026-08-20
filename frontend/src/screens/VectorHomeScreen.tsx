import { useEffect, useMemo, useState } from "react";
import { acceptDevelopmentConsent, fetchDevelopmentHome } from "../api/development";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { MonoLabel } from "../components/MonoLabel";
import { SkeletonCard } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import { useHome } from "../hooks/useHome";
import type { DevelopmentHome, VectorDimension } from "../types/development";

const ERA_PRO_THRESHOLD = 8_000;
const DIMENSION_ORDER: VectorDimension[] = ["energy", "agency", "autonomy", "connection", "direction"];
const DIMENSION_LABELS: Record<VectorDimension, string> = {
  energy: "Энергия",
  agency: "Действие",
  autonomy: "Самостоятельность",
  connection: "Связь",
  direction: "Направление",
};

function formatPoints(value: number): string {
  return new Intl.NumberFormat("ru-RU").format(value);
}

function monthLabel(value: string | null | undefined): string {
  if (!value) return "Пока нет данных";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("ru-RU", { month: "long", year: "numeric" });
}

export function VectorHomeScreen({
  onNavigate,
  onBack,
}: {
  onNavigate: (route: "checkin" | "assessments" | "history" | "goals" | "privacy") => void;
  onBack?: () => void;
}) {
  const growth = useHome();
  const [development, setDevelopment] = useState<DevelopmentHome | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [consentBusy, setConsentBusy] = useState(false);

  async function loadDevelopment() {
    setLoading(true);
    setError(false);
    try {
      setDevelopment(await fetchDevelopmentHome());
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadDevelopment(); }, []);

  const dimensions = useMemo(() => {
    if (!development?.profile?.state) return [];
    return DIMENSION_ORDER
      .map((key) => ({ key, value: development.profile?.state[key] }))
      .filter((item): item is { key: VectorDimension; value: number } => typeof item.value === "number");
  }, [development]);

  if (growth.status === "loading" || loading) {
    return <div className="era-page" style={{ padding: "1.2rem", display: "grid", gap: "0.8rem" }}>{onBack && <button type="button" onClick={onBack}>← Назад</button>}<SkeletonCard /><SkeletonCard /><SkeletonCard /></div>;
  }
  if (growth.status === "error" || error || !development) {
    return <StatusBanner title="Не удалось открыть «Мой вектор»" description="Попробуйте открыть раздел ещё раз." />;
  }

  if (development.consent_required) {
    return (
      <div className="era-page" style={{ padding: "1.2rem", display: "flex", flexDirection: "column", gap: "0.9rem" }}>
        {onBack && <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← Назад</button>}
        <Card gradient>
          <MonoLabel tone="violet">Мой вектор</MonoLabel>
          <h1 style={{ margin: "0.35rem 0 0", fontFamily: "var(--era-font-display)", fontSize: "1.7rem" }}>Твой личный маршрут роста</h1>
          <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-secondary)", lineHeight: 1.5 }}>Вектор объединяет цели, активность и личную динамику. Психологические ответы не используются для рейтинга участников.</p>
        </Card>
        <Card>
          <strong>Перед началом</strong>
          <p style={{ color: "var(--era-text-secondary)", lineHeight: 1.5 }}>Ты видишь весь личный профиль. Команда ЭРА получает только разрешённые итоговые показатели и динамику; личные заметки остаются приватными.</p>
          <button type="button" className="era-btn-primary" disabled={consentBusy} onClick={async () => {
            setConsentBusy(true);
            try {
              await acceptDevelopmentConsent(true);
              await loadDevelopment();
            } finally {
              setConsentBusy(false);
            }
          }}>{consentBusy ? "Сохраняем…" : "Понятно, продолжить"}</button>
        </Card>
      </div>
    );
  }

  const data = growth.data;
  const remaining = Math.max(0, ERA_PRO_THRESHOLD - data.points_balance);
  const proPercent = Math.min(100, Math.round((data.points_balance / ERA_PRO_THRESHOLD) * 100));
  const nextAction = data.next_step;

  return (
    <div className="era-page era-stagger" style={{ padding: "1.15rem 1.15rem var(--era-page-bottom-safe)", display: "flex", flexDirection: "column", gap: "1rem" }}>
      {onBack && <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← Назад</button>}
      <div>
        <MonoLabel tone="violet">Мой вектор</MonoLabel>
        <h1 style={{ margin: "0.3rem 0 0", fontFamily: "var(--era-font-display)", fontSize: "1.8rem" }}>Где ты сейчас и куда двигаться дальше</h1>
        <p style={{ margin: "0.45rem 0 0", color: "var(--era-text-muted)", lineHeight: 1.5 }}>Сейчас → цель → действия → результат → следующий уровень.</p>
      </div>

      <section style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
        <MonoLabel>Сейчас</MonoLabel>
        <Card gradient>
          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.8rem", alignItems: "flex-start" }}>
            <div><strong style={{ display: "block", fontSize: "1.2rem" }}>{data.growth.label}</strong><span style={{ display: "block", marginTop: "0.2rem", color: "var(--era-text-secondary)" }}>{formatPoints(data.points_balance)} баллов</span></div>
            {development.profile?.index != null && <div style={{ textAlign: "right" }}><strong style={{ display: "block", fontSize: "1.2rem" }}>{Math.round(development.profile.index)}</strong><span style={{ color: "var(--era-text-muted)", fontSize: "0.72rem" }}>индекс вектора</span></div>}
          </div>
          {dimensions.length > 0 && <div style={{ display: "grid", gridTemplateColumns: "repeat(5,minmax(0,1fr))", gap: "0.35rem", marginTop: "0.9rem" }}>{dimensions.map(({ key, value }) => <div key={key} style={{ textAlign: "center", minWidth: 0 }}><strong style={{ display: "block" }}>{Math.round(value)}</strong><span style={{ display: "block", marginTop: "0.12rem", color: "var(--era-text-muted)", fontSize: "0.62rem", overflow: "hidden", textOverflow: "ellipsis" }}>{DIMENSION_LABELS[key]}</span></div>)}</div>}
          <p style={{ margin: "0.8rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8rem" }}>Последний снимок: {monthLabel(development.profile?.last_checkin_at)}</p>
        </Card>
      </section>

      <section style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.7rem", alignItems: "center" }}><MonoLabel>Мои цели</MonoLabel><button type="button" className="era-btn-ghost" onClick={() => onNavigate("goals")}>Все →</button></div>
        {development.current_goal ? <Card onClick={() => onNavigate("goals")}><strong>{development.current_goal.title}</strong><p style={{ margin: "0.3rem 0 0", color: "var(--era-text-secondary)", fontSize: "0.82rem" }}>{development.current_goal.experiment || "Текущий фокус месяца"}</p><span style={{ display: "block", marginTop: "0.45rem", color: "var(--era-violet)", fontWeight: 800, fontSize: "0.8rem" }}>Открыть цель →</span></Card> : <Card onClick={() => onNavigate("goals")}><strong>Выбери один фокус на месяц</strong><p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)", fontSize: "0.82rem" }}>Не список обещаний — один реальный эксперимент.</p></Card>}
      </section>

      <section style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
        <MonoLabel>Мой рост</MonoLabel>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: "0.55rem" }}>
          <Metric label="Проекты" value={data.activity.projects} />
          <Metric label="Завершённые задачи" value={data.activity.completed_tasks} />
          <Metric label="Результаты в портфолио" value={data.activity.portfolio_items} />
          <Metric label="Баллы за месяц" value={data.points_month} />
        </div>
        <Card onClick={() => onNavigate("assessments")}><strong>Навыки и исследования</strong><p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)", fontSize: "0.82rem" }}>Инструменты, которые помогают увидеть устойчивые особенности и сильные стороны.</p><span style={{ display: "block", marginTop: "0.45rem", color: "var(--era-violet)", fontWeight: 800, fontSize: "0.8rem" }}>Открыть исследования →</span></Card>
      </section>

      <section style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.7rem", alignItems: "center" }}><MonoLabel>Моя история</MonoLabel><button type="button" className="era-btn-ghost" onClick={() => onNavigate("history")}>Открыть →</button></div>
        <Card onClick={() => onNavigate("history")}><strong>История изменений</strong><p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)", fontSize: "0.82rem" }}>Check-in, личные выводы, цели и динамика собираются в хронологию, чтобы сравнивать себя прежде всего с собой.</p></Card>
      </section>

      <section style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
        <MonoLabel>Следующий уровень</MonoLabel>
        <Card style={{ borderColor: remaining === 0 ? "rgba(99,44,255,.3)" : undefined }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.7rem" }}><strong>ЭРА PRO</strong><strong>{proPercent}%</strong></div>
          <div style={{ height: 7, marginTop: "0.5rem", background: "var(--era-ring-track)", borderRadius: 999, overflow: "hidden" }}><div style={{ width: `${proPercent}%`, height: "100%", background: "var(--era-gradient-signal)" }} /></div>
          <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-secondary)", fontSize: "0.82rem" }}>{remaining > 0 ? `Не хватает ${formatPoints(remaining)} баллов до права подать заявку.` : "Порог достигнут. Можно подать заявку — баллы не списываются."}</p>
          <button type="button" onClick={() => { window.location.hash = "#/era-pro"; }} style={{ marginTop: "0.65rem" }}>{remaining > 0 ? "Посмотреть ЭРА PRO" : "Подать заявку в ЭРА PRO"} →</button>
        </Card>
      </section>

      <section style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
        <MonoLabel>Рекомендация</MonoLabel>
        {nextAction ? <Card onClick={() => {
          if (nextAction.kind === "project" && nextAction.entity_id) window.location.hash = `#/projects/${nextAction.entity_id}`;
          else if (nextAction.kind === "event" && nextAction.entity_id) window.location.hash = `#/events/${nextAction.entity_id}`;
          else if (nextAction.kind === "task" && nextAction.entity_id) window.location.hash = `#/tasks/${nextAction.entity_id}`;
          else if (nextAction.kind === "opportunity" && nextAction.entity_id) window.location.hash = `#/opportunities/${nextAction.entity_id}`;
          else if (nextAction.kind === "growth") onNavigate("checkin");
        }}><strong>{nextAction.title}</strong><p style={{ margin: "0.3rem 0 0", color: "var(--era-text-secondary)", fontSize: "0.82rem" }}>{nextAction.description}</p><span style={{ display: "block", marginTop: "0.45rem", color: "var(--era-violet)", fontWeight: 800, fontSize: "0.8rem" }}>Перейти к действию →</span></Card> : <EmptyState text="Сейчас система не видит срочного следующего шага. Выбери одну цель и продолжай подтверждённую активность." />}
      </section>

      <button type="button" onClick={() => onNavigate("privacy")}>Данные и приватность</button>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return <Card style={{ padding: "0.8rem" }}><strong style={{ display: "block", fontSize: "1.25rem" }}>{value}</strong><span style={{ display: "block", marginTop: "0.15rem", color: "var(--era-text-muted)", fontSize: "0.75rem" }}>{label}</span></Card>;
}
