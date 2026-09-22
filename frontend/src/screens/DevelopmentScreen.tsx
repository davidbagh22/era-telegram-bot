import { useEffect, useMemo, useState } from "react";

import {
  acceptDevelopmentConsent,
  completeCheckin,
  createDevelopmentGoal,
  fetchCurrentCheckin,
  fetchDevelopmentHistory,
  fetchDevelopmentHome,
  fetchDevelopmentPrivacy,
  reviewDevelopmentGoal,
  saveCheckinAnswer,
  updateDevelopmentPrivacy,
} from "../api/development";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { MonoLabel } from "../components/MonoLabel";
import { SkeletonCard } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import { useToast } from "../components/Toast";
import type {
  DevelopmentHome,
  DevelopmentPrivacy,
  VectorCheckin,
  VectorDimension,
} from "../types/development";
import { AssessmentExperience } from "./AssessmentExperience";

export type DevelopmentRoute = "home" | "checkin" | "assessments" | "history" | "goals" | "privacy";

const DIMENSIONS: VectorDimension[] = ["energy", "agency", "autonomy", "connection", "direction"];
const DEFAULT_LABELS: Record<VectorDimension, string> = {
  energy: "Энергия",
  agency: "Действие",
  autonomy: "Самостоятельность",
  connection: "Связь",
  direction: "Направление",
};

function Header({ title, onBack }: { title: string; onBack?: () => void }) {
  return (
    <header style={{ display: "flex", alignItems: "center", gap: ".7rem" }}>
      {onBack && <button type="button" onClick={onBack} style={{ minWidth: 44, minHeight: 44 }}>←</button>}
      <h1 style={{ margin: 0, fontFamily: "var(--era-font-display)", fontSize: "1.65rem", lineHeight: 1.1 }}>{title}</h1>
    </header>
  );
}

export function DevelopmentScreen({
  route = "home",
  onNavigate,
  onBack,
}: {
  route?: DevelopmentRoute;
  onNavigate?: (route: DevelopmentRoute) => void;
  onBack?: () => void;
}) {
  const [home, setHome] = useState<DevelopmentHome | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const toast = useToast();

  async function refresh() {
    setLoading(true);
    setError(false);
    try {
      setHome(await fetchDevelopmentHome());
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, []);

  const goHome = () => {
    if (onNavigate) onNavigate("home");
    else onBack?.();
  };

  if (loading) {
    return <div className="era-page" style={{ padding: "1rem", display: "grid", gap: "1rem" }}><SkeletonCard /><SkeletonCard /><SkeletonCard /></div>;
  }
  if (error || !home) {
    return <StatusBanner title="Не удалось открыть «Мой вектор»" description="Проверь соединение и попробуй снова." />;
  }

  if (home.consent_required) {
    return (
      <div className="era-page" style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <Header title="Кто увидит результаты?" onBack={onBack} />
        <Card>
          <strong>Ты</strong>
          <p style={{ color: "var(--era-text-secondary)", lineHeight: 1.5 }}>Видишь личный профиль, историю и цели.</p>
          <strong>Команда ЭРА</strong>
          <p style={{ color: "var(--era-text-secondary)", lineHeight: 1.5 }}>Видит только разрешённые итоговые показатели и динамику — без личных заметок и психологического рейтинга.</p>
        </Card>
        <button type="button" className="era-btn-primary" onClick={async () => {
          try {
            await acceptDevelopmentConsent(true);
            await refresh();
          } catch {
            toast.show("Не удалось сохранить согласие. Попробуй ещё раз.", "error");
          }
        }}>Понятно, продолжить</button>
      </div>
    );
  }

  if (route === "checkin") return <MonthlyMarkScreen home={home} onDone={refresh} onBack={goHome} />;
  if (route === "assessments") return <AssessmentExperience onBack={goHome} />;
  if (route === "history") return <HistoryScreen labels={home.state_labels} onBack={goHome} />;
  if (route === "goals") return <GoalsScreen home={home} onRefresh={refresh} onBack={goHome} />;
  if (route === "privacy") return <PrivacyScreen onBack={goHome} />;

  return (
    <div className="era-page" style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <Header title="Мой вектор" onBack={onBack} />
      <p style={{ margin: 0, color: "var(--era-text-secondary)", lineHeight: 1.5 }}>{home.subtitle}</p>
      <Card onClick={() => onNavigate?.("checkin")} style={{ borderLeft: "3px solid var(--era-violet)" }}>
        <MonoLabel tone="violet">ЕЖЕМЕСЯЧНАЯ ОТМЕТКА</MonoLabel>
        <strong style={{ display: "block", marginTop: ".35rem" }}>{home.current_checkin?.status === "completed" ? "Посмотреть отметку за месяц" : "Отметиться за месяц"}</strong>
        <span style={{ display: "block", marginTop: ".25rem", color: "var(--era-text-muted)", fontSize: ".8rem" }}>5–8 минут · можно продолжить позже</span>
      </Card>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".65rem" }}>
        <MiniAction title="История" text="Твоя динамика по месяцам" onClick={() => onNavigate?.("history")} />
        <MiniAction title="Исследования" text="Навыки и сильные стороны" onClick={() => onNavigate?.("assessments")} />
        <MiniAction title="Мои цели" text="Один фокус и реальный шаг" onClick={() => onNavigate?.("goals")} />
        <MiniAction title="Приватность" text="Что видишь ты и команда" onClick={() => onNavigate?.("privacy")} />
      </div>
    </div>
  );
}

function MiniAction({ title, text, onClick }: { title: string; text: string; onClick: () => void }) {
  return (
    <Card onClick={onClick} style={{ minHeight: 108 }}>
      <strong>{title}</strong>
      <span style={{ display: "block", marginTop: ".3rem", color: "var(--era-text-muted)", fontSize: ".8rem", lineHeight: 1.4 }}>{text}</span>
    </Card>
  );
}

function MonthlyMarkScreen({ home, onDone, onBack }: { home: DevelopmentHome; onDone: () => Promise<void>; onBack: () => void }) {
  const toast = useToast();
  const [mark, setMark] = useState<VectorCheckin | null>(home.current_checkin);
  const firstMissing = useMemo(() => {
    const index = home.questions.findIndex((question) => home.current_checkin?.answers?.[question.code] === undefined);
    return index === -1 ? 0 : index;
  }, [home.current_checkin, home.questions]);
  const [cursor, setCursor] = useState(firstMissing);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (mark) return;
    void fetchCurrentCheckin()
      .then(setMark)
      .catch(() => toast.show("Не удалось загрузить ежемесячную отметку.", "error"));
  }, [mark, toast]);

  if (!mark) return <div className="era-page" style={{ padding: "1rem" }}><SkeletonCard /></div>;

  if (mark.status === "completed") {
    return (
      <div className="era-page" style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <Header title="Ежемесячная отметка" onBack={onBack} />
        <Card gradient>
          <MonoLabel tone="violet">ГОТОВО</MonoLabel>
          <strong style={{ display: "block", marginTop: ".35rem", fontSize: "1.15rem" }}>{mark.insight.title || "Отметка сохранена"}</strong>
          {mark.insight.insight && <p style={{ color: "var(--era-text-secondary)", lineHeight: 1.5 }}>{mark.insight.insight}</p>}
          {mark.insight.focus && <p style={{ color: "var(--era-text-secondary)", lineHeight: 1.5 }}>Фокус: {mark.insight.focus}</p>}
        </Card>
        <StateGrid state={mark.state} labels={home.state_labels} />
      </div>
    );
  }

  const question = home.questions[cursor];
  if (!question) {
    return <StatusBanner title="Отметка недоступна" description="В этом месяце пока нет вопросов." />;
  }
  const answeredCount = Object.keys(mark.answers).length;
  const allAnswered = home.questions.every((item) => mark.answers[item.code] !== undefined);

  async function choose(value: number) {
    if (busy) return;
    setBusy(true);
    try {
      const nextAnswers = { ...mark!.answers, [question.code]: value };
      const next = await saveCheckinAnswer(nextAnswers, mark!.context.factors, mark!.context.development_wants);
      setMark(next);
      const nextIndex = home.questions.findIndex((item, index) => index > cursor && next.answers[item.code] === undefined);
      if (nextIndex >= 0) setCursor(nextIndex);
    } catch {
      toast.show("Ответ не сохранился. Попробуй ещё раз.", "error");
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    if (!allAnswered || busy) return;
    setBusy(true);
    try {
      const done = await completeCheckin();
      setMark(done);
      await onDone();
      toast.show("Ежемесячная отметка сохранена", "success");
    } catch {
      toast.show("Не удалось завершить отметку. Проверь ответы.", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="era-page" style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <Header title="Ежемесячная отметка" onBack={onBack} />
      <div style={{ display: "flex", justifyContent: "space-between", gap: ".7rem", color: "var(--era-text-muted)", fontSize: ".8rem" }}>
        <span>{answeredCount} из {home.questions.length}</span>
        <span>Можно продолжить позже</span>
      </div>
      <Card>
        {question.theme && <MonoLabel>{question.theme}</MonoLabel>}
        <strong style={{ display: "block", marginTop: ".35rem", fontSize: "1.1rem" }}>{question.title}</strong>
        <p style={{ color: "var(--era-text-secondary)", lineHeight: 1.5 }}>{question.text}</p>
        <div style={{ display: "grid", gap: ".5rem", marginTop: ".8rem" }}>
          {home.answer_options.map((option) => {
            const selected = mark.answers[question.code] === option.value;
            return (
              <button key={option.value} type="button" disabled={busy} onClick={() => void choose(option.value)} className={selected ? "era-btn-primary" : "era-btn-secondary"} style={{ minHeight: 44 }}>
                {option.label}
              </button>
            );
          })}
        </div>
      </Card>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: ".5rem" }}>
        <button type="button" disabled={cursor === 0} onClick={() => setCursor((value) => Math.max(0, value - 1))}>← Назад</button>
        <button type="button" disabled={cursor >= home.questions.length - 1} onClick={() => setCursor((value) => Math.min(home.questions.length - 1, value + 1))}>Дальше →</button>
      </div>
      <button type="button" className="era-btn-primary" disabled={!allAnswered || busy} onClick={() => void finish()} style={{ minHeight: 48 }}>
        {busy ? "Сохраняем…" : "Завершить отметку"}
      </button>
    </div>
  );
}

function StateGrid({ state, labels }: { state: Partial<Record<VectorDimension, number>>; labels: Record<VectorDimension, string> }) {
  const values = DIMENSIONS.filter((key) => typeof state[key] === "number");
  if (!values.length) return <EmptyState text="Данных пока нет." />;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".6rem" }}>
      {values.map((key) => (
        <Card key={key} style={{ padding: ".8rem" }}>
          <strong style={{ display: "block", fontSize: "1.15rem" }}>{Math.round(state[key] ?? 0)}</strong>
          <span style={{ color: "var(--era-text-muted)", fontSize: ".8rem" }}>{labels[key] || DEFAULT_LABELS[key]}</span>
        </Card>
      ))}
    </div>
  );
}

function HistoryScreen({ labels, onBack }: { labels: Record<VectorDimension, string>; onBack: () => void }) {
  const [items, setItems] = useState<VectorCheckin[] | null>(null);
  useEffect(() => {
    void fetchDevelopmentHistory().then(setItems).catch(() => setItems([]));
  }, []);
  return (
    <div className="era-page" style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <Header title="История изменений" onBack={onBack} />
      {!items ? <SkeletonCard /> : items.length === 0 ? <EmptyState text="История появится после первой ежемесячной отметки." /> : items.map((item) => (
        <Card key={item.id}>
          <MonoLabel>{new Date(`${item.month}-01T00:00:00`).toLocaleDateString("ru-RU", { month: "long", year: "numeric" })}</MonoLabel>
          <strong style={{ display: "block", marginTop: ".35rem" }}>{item.insight.title || "Ежемесячная отметка"}</strong>
          {item.insight.insight && <p style={{ color: "var(--era-text-secondary)", lineHeight: 1.5 }}>{item.insight.insight}</p>}
          <StateGrid state={item.state} labels={labels} />
        </Card>
      ))}
    </div>
  );
}

function GoalsScreen({ home, onRefresh, onBack }: { home: DevelopmentHome; onRefresh: () => Promise<void>; onBack: () => void }) {
  const toast = useToast();
  const [title, setTitle] = useState("");
  const [experiment, setExperiment] = useState("");
  const [busy, setBusy] = useState(false);

  async function createGoal() {
    if (!title.trim() || busy) return;
    setBusy(true);
    try {
      await createDevelopmentGoal({ title: title.trim(), experiment: experiment.trim() || null, is_custom: true });
      setTitle("");
      setExperiment("");
      await onRefresh();
      toast.show("Фокус сохранён", "success");
    } catch {
      toast.show("Не удалось сохранить фокус.", "error");
    } finally {
      setBusy(false);
    }
  }

  async function review(result: string) {
    if (!home.current_goal || busy) return;
    setBusy(true);
    try {
      await reviewDevelopmentGoal(home.current_goal.id, result);
      await onRefresh();
      toast.show("Итог сохранён", "success");
    } catch {
      toast.show("Не удалось сохранить итог.", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="era-page" style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <Header title="Мои цели" onBack={onBack} />
      {home.current_goal ? (
        <Card>
          <MonoLabel>ФОКУС МЕСЯЦА</MonoLabel>
          <strong style={{ display: "block", marginTop: ".35rem" }}>{home.current_goal.title}</strong>
          {home.current_goal.experiment && <p style={{ color: "var(--era-text-secondary)", lineHeight: 1.5 }}>{home.current_goal.experiment}</p>}
          {!home.current_goal.review && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".5rem", marginTop: ".8rem" }}>
              <button type="button" disabled={busy} onClick={() => void review("done")}>Сделал</button>
              <button type="button" disabled={busy} onClick={() => void review("partial")}>Частично</button>
              <button type="button" disabled={busy} onClick={() => void review("not_done")}>Не получилось</button>
              <button type="button" disabled={busy} onClick={() => void review("changed_mind")}>Передумал</button>
            </div>
          )}
        </Card>
      ) : (
        <Card>
          <strong>Один фокус на месяц</strong>
          <p style={{ color: "var(--era-text-secondary)", lineHeight: 1.5 }}>Выбери то, что действительно хочешь проверить действием.</p>
          <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Например: чаще брать инициативу" aria-label="Фокус месяца" style={{ width: "100%", minHeight: 44, marginTop: ".6rem" }} />
          <textarea value={experiment} onChange={(event) => setExperiment(event.target.value)} placeholder="Какой маленький шаг ты попробуешь?" aria-label="Эксперимент месяца" rows={3} style={{ width: "100%", marginTop: ".6rem" }} />
          <button type="button" className="era-btn-primary" disabled={busy || !title.trim()} onClick={() => void createGoal()} style={{ marginTop: ".6rem" }}>Сохранить фокус</button>
        </Card>
      )}
    </div>
  );
}

function PrivacyScreen({ onBack }: { onBack: () => void }) {
  const toast = useToast();
  const [privacy, setPrivacy] = useState<DevelopmentPrivacy | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void fetchDevelopmentPrivacy().then(setPrivacy).catch(() => setPrivacy(null));
  }, []);

  if (!privacy) return <div className="era-page" style={{ padding: "1rem" }}><SkeletonCard /></div>;

  async function toggle(key: keyof DevelopmentPrivacy["admin_visibility"]) {
    if (busy) return;
    const next = { ...privacy.admin_visibility, [key]: !privacy.admin_visibility[key] };
    setBusy(true);
    try {
      await updateDevelopmentPrivacy(next);
      setPrivacy({ ...privacy, admin_visibility: next });
    } catch {
      toast.show("Не удалось обновить настройку.", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="era-page" style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <Header title="Данные и приватность" onBack={onBack} />
      <Card>
        <strong>Что может видеть команда ЭРА</strong>
        <div style={{ display: "grid", gap: ".55rem", marginTop: ".8rem" }}>
          {(["summary", "interests", "goals"] as const).map((key) => (
            <label key={key} style={{ display: "flex", justifyContent: "space-between", gap: ".8rem", alignItems: "center", minHeight: 44 }}>
              <span>{key === "summary" ? "Итоговую динамику" : key === "interests" ? "Интересы" : "Цели"}</span>
              <input type="checkbox" checked={privacy.admin_visibility[key]} disabled={busy} onChange={() => void toggle(key)} />
            </label>
          ))}
        </div>
      </Card>
      <Card>
        <strong>Всегда остаётся личным</strong>
        <p style={{ color: "var(--era-text-secondary)", lineHeight: 1.5 }}>{privacy.private_only.join(" · ")}</p>
      </Card>
    </div>
  );
}
