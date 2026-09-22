import { useEffect, useMemo, useState } from "react";
import { acceptDevelopmentConsent, fetchDevelopmentHome } from "../api/development";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { MonoLabel } from "../components/MonoLabel";
import { SkeletonCard } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import type { DevelopmentHome, VectorDimension } from "../types/development";

const DIMENSION_ORDER: VectorDimension[] = ["energy", "agency", "autonomy", "connection", "direction"];
const DIMENSION_LABELS: Record<VectorDimension, string> = {
  energy: "Энергия",
  agency: "Действие",
  autonomy: "Самостоятельность",
  connection: "Связь",
  direction: "Направление",
};

function monthLabel(value: string | null | undefined): string {
  if (!value) return "Пока нет отметок";
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

  if (loading) {
    return <div className="era-page" style={{ padding: "1rem", display: "grid", gap: "0.8rem" }}>{onBack && <button type="button" onClick={onBack}>← Назад</button>}<SkeletonCard /><SkeletonCard /><SkeletonCard /></div>;
  }
  if (error || !development) {
    return <StatusBanner title="Не удалось открыть «Мой вектор»" description="Попробуй открыть раздел ещё раз." />;
  }

  if (development.consent_required) {
    return (
      <div className="era-page" style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        {onBack && <button type="button" onClick={onBack} style={{ alignSelf: "flex-start", minHeight: 44 }}>← Назад</button>}
        <Card gradient>
          <MonoLabel tone="violet">Мой вектор</MonoLabel>
          <h1 style={{ margin: ".4rem 0 0", fontFamily: "var(--era-font-display)", fontSize: "1.8rem" }}>Твой личный маршрут развития</h1>
          <p style={{ margin: ".55rem 0 0", color: "var(--era-text-secondary)", lineHeight: 1.5 }}>Вектор помогает замечать изменения, выбирать фокус и сравнивать себя только с собой.</p>
        </Card>
        <Card>
          <strong>Перед началом</strong>
          <p style={{ color: "var(--era-text-secondary)", lineHeight: 1.5 }}>Ты видишь весь личный профиль. Команда ЭРА получает только разрешённые итоговые показатели и динамику. Личные заметки остаются приватными.</p>
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

  return (
    <div className="era-page era-stagger" style={{ padding: "1rem 1rem var(--era-page-bottom-safe)", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {onBack && <button type="button" onClick={onBack} style={{ alignSelf: "flex-start", minHeight: 44 }}>← Назад</button>}
      <header>
        <MonoLabel tone="violet">Мой вектор</MonoLabel>
        <h1 style={{ margin: ".35rem 0 0", fontFamily: "var(--era-font-display)", fontSize: "1.8rem", lineHeight: 1.08 }}>Где ты сейчас и куда двигаться дальше</h1>
        <p style={{ margin: ".5rem 0 0", color: "var(--era-text-secondary)", fontSize: ".9rem", lineHeight: 1.5 }}>Отметь состояние, выбери один фокус и посмотри динамику без рейтингов и соревнования.</p>
      </header>

      <section style={{ display: "flex", flexDirection: "column", gap: ".65rem" }}>
        <MonoLabel>Сейчас</MonoLabel>
        {dimensions.length > 0 ? (
          <Card>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: ".7rem" }}>
              {dimensions.map(({ key, value }) => (
                <div key={key} style={{ padding: ".7rem", borderRadius: "var(--era-radius-md)", background: "var(--era-surface-2)" }}>
                  <strong style={{ display: "block", fontSize: "1.15rem" }}>{Math.round(value)}</strong>
                  <span style={{ display: "block", marginTop: ".15rem", color: "var(--era-text-secondary)", fontSize: ".8rem" }}>{DIMENSION_LABELS[key]}</span>
                </div>
              ))}
            </div>
            <p style={{ margin: ".8rem 0 0", color: "var(--era-text-muted)", fontSize: ".8rem" }}>Последняя отметка: {monthLabel(development.profile?.last_checkin_at)}</p>
          </Card>
        ) : <EmptyState text="Сделай первую ежемесячную отметку — здесь появится твоя динамика." />}

        <Card onClick={() => onNavigate("checkin")} style={{ borderLeft: "3px solid var(--era-violet)" }}>
          <strong>{development.current_checkin?.status === "completed" ? "Посмотреть отметку за месяц" : "Отметиться за месяц"}</strong>
          <span style={{ display: "block", marginTop: ".25rem", color: "var(--era-text-muted)", fontSize: ".8rem" }}>Ежемесячная отметка · можно продолжить позже</span>
        </Card>
      </section>

      <section style={{ display: "flex", flexDirection: "column", gap: ".65rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: ".7rem", alignItems: "center" }}>
          <MonoLabel>Мой фокус</MonoLabel>
          <button type="button" className="era-btn-ghost" onClick={() => onNavigate("goals")}>Все →</button>
        </div>
        {development.current_goal ? (
          <Card onClick={() => onNavigate("goals")}>
            <strong>{development.current_goal.title}</strong>
            <p style={{ margin: ".35rem 0 0", color: "var(--era-text-secondary)", fontSize: ".85rem" }}>{development.current_goal.experiment || "Текущий фокус месяца"}</p>
          </Card>
        ) : (
          <Card onClick={() => onNavigate("goals")}>
            <strong>Выбери один фокус на месяц</strong>
            <p style={{ margin: ".35rem 0 0", color: "var(--era-text-muted)", fontSize: ".85rem" }}>Не список обещаний — один реальный шаг, который можно проверить.</p>
          </Card>
        )}
      </section>

      <section style={{ display: "flex", flexDirection: "column", gap: ".65rem" }}>
        <MonoLabel>Инструменты развития</MonoLabel>
        <Card onClick={() => onNavigate("assessments")}>
          <strong>Навыки и исследования</strong>
          <p style={{ margin: ".35rem 0 0", color: "var(--era-text-muted)", fontSize: ".85rem" }}>Инструменты, которые помогают увидеть устойчивые особенности и сильные стороны.</p>
        </Card>
        <Card onClick={() => onNavigate("history")}>
          <strong>История изменений</strong>
          <p style={{ margin: ".35rem 0 0", color: "var(--era-text-muted)", fontSize: ".85rem" }}>Ежемесячные отметки, цели и личные выводы — в одной хронологии.</p>
        </Card>
      </section>

      <button type="button" onClick={() => onNavigate("privacy")} style={{ minHeight: 44 }}>Данные и приватность</button>
    </div>
  );
}
