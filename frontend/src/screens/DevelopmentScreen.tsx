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
  savePersonalNote,
  updateDevelopmentPrivacy,
} from "../api/development";
import { Card } from "../components/Card";
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
const RING_COLORS = ["var(--era-red)", "#8f1e2e", "var(--era-gold-ink)", "#4b4a50", "#c9c5bf"];

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

  useEffect(() => {
    void refresh();
  }, []);

  const goHome = () => {
    if (onNavigate) onNavigate("home");
    else onBack?.();
  };

  if (loading) {
    return (
      <div className="era-page" style={{ padding: "1.2rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }
  if (error || !home) {
    return <StatusBanner title="Не удалось открыть «Мой вектор»" description="Проверь соединение и попробуй снова." />;
  }
  if (home.consent_required) {
    return (
      <ConsentScreen
        onAccept={async () => {
          try {
            await acceptDevelopmentConsent(true);
            await refresh();
          } catch {
            toast.show("Не удалось сохранить согласие. Попробуй ещё раз.", "error");
          }
        }}
        onBack={onBack}
      />
    );
  }
  if (route === "checkin") return <CheckinScreen home={home} onDone={refresh} onBack={goHome} />;
  if (route === "assessments") return <AssessmentExperience onBack={goHome} />;
  if (route === "history") return <HistoryScreen labels={home.state_labels} onBack={goHome} />;
  if (route === "goals") return <GoalsScreen home={home} onRefresh={refresh} onBack={goHome} />;
  if (route === "privacy") return <PrivacyScreen onBack={goHome} />;

  return (
    <div className="era-page" style={{ padding: "1.15rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <Header title="Мой вектор" onBack={onBack} />
      <p style={{ margin: 0, color: "var(--era-text-muted)" }}>{home.subtitle}</p>
      <Card gradient>
        <SegmentedRing index={home.profile?.index ?? null} state={home.profile?.state ?? {}} labels={home.state_labels} />
        <p style={{ textAlign: "center", color: "rgba(255,255,255,.72)" }}>
          {home.profile?.notice ?? "Пройди короткий Check-in, чтобы получить первый снимок состояния."}
        </p>
      </Card>
      <Card onClick={() => onNavigate?.("checkin")} style={{ borderLeft: "3px solid var(--era-red)" }}>
        <small>ТВОЙ CHECK-IN</small>
        <strong style={{ display: "block", marginTop: 4 }}>
          {home.current_checkin?.status === "completed" ? "Посмотреть результат месяца" : "Посмотрим, что изменилось?"}
        </strong>
        <span style={{ display: "block", marginTop: 4, color: "var(--era-text-muted)" }}>
          5–8 минут · можно продолжить позже
        </span>
      </Card>
      {home.current_goal ? (
        <Card onClick={() => onNavigate?.("goals")}>
          <small>ФОКУС МЕСЯЦА</small>
          <strong style={{ display: "block", marginTop: 4 }}>{home.current_goal.title}</strong>
        </Card>
      ) : null}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 8 }}>
        <MiniAction title="Моя карта" text="Состояние и опоры" onClick={() => onNavigate?.("checkin")} />
        <MiniAction title="Мой год" text="Динамика по месяцам" onClick={() => onNavigate?.("history")} />
        <MiniAction title="Исследования" text="10 направлений" onClick={() => onNavigate?.("assessments")} />
        <MiniAction title="Мои цели" text="Один фокус и реальный эксперимент" onClick={() => onNavigate?.("goals")} />
      </div>
      <button onClick={() => onNavigate?.("privacy")}>Данные и приватность</button>
    </div>
  );
}

function ConsentScreen({ onAccept, onBack }: { onAccept: () => void; onBack?: () => void }) {
  return (
    <div className="era-page" style={{ padding: "1.2rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <Header title="Кто увидит результаты?" onBack={onBack} />
      <Card>
        <strong>Ты</strong>
        <p>Видишь весь личный профиль, историю, цели, заметки и рекомендации.</p>
        <strong>Команда ЭРА</strong>
        <p>Видит только разрешённые итоговые показатели и динамику.</p>
        <strong>Только ты</strong>
        <p>Личные заметки, свободные записи, черновики и скрытые выводы.</p>
      </Card>
      <Card>
        <strong>Важно</strong>
        <p>Здесь нет диагнозов, психологических рейтингов и автоматического отбора в проекты или роли.</p>
      </Card>
      <button className="era-btn-primary" onClick={onAccept}>Понятно, продолжить</button>
    </div>
  );
}

function CheckinScreen({
  home,
  onDone,
  onBack,
}: {
  home: DevelopmentHome;
  onDone: () => Promise<void>;
  onBack: () => void;
}) {
  const toast = useToast();
  const [checkin, setCheckin] = useState<VectorCheckin | null>(home.current_checkin);
  const [busy, setBusy] = useState(false);
  const [factors, setFactors] = useState<string[]>(home.current_checkin?.context.factors ?? []);
  const [wants, setWants] = useState<string[]>(home.current_checkin?.context.development_wants ?? []);
  const [why, setWhy] = useState(false);
  const [note, setNote] = useState("");
  const [goalReviewed, setGoalReviewed] = useState(Boolean(home.current_goal?.review));

  useEffect(() => {
    if (!checkin) {
      void fetchCurrentCheckin().then(setCheckin).catch(() => toast.show("Не удалось загрузить Check-in.", "error"));
    }
  }, [checkin, toast]);

  const unanswered = useMemo(
    () => home.questions.find((question) => checkin?.answers?.[question.code] === undefined),
    [home.questions, checkin],
  );

  if (!checkin) return <div className="era-page" style={{ padding: "1.2rem" }}><SkeletonCard /></div>;

  if (home.current_goal && home.current_goal.month < checkin.month && !goalReviewed && checkin.status !== "completed") {
    return (
      <div className="era-page" style={{ padding: "1.2rem", display: "grid", gap: 10 }}>
        <Header title="Сначала — прошлый месяц" onBack={onBack} />
        <Card><p>В прошлом месяце ты хотел…</p><strong>{home.current_goal.title}</strong></Card>
        {[
          ["done", "Сделал"],
          ["partial", "Частично"],
          ["not_done", "Не получилось"],
          ["changed_mind", "Передумал"],
          ["lost_meaning", "Цель потеряла смысл"],
        ].map(([value, label]) => (
          <button
            key={value}
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await reviewDevelopmentGoal(home.current_goal!.id, value);
                setGoalReviewed(true);
              } catch {
                toast.show("Не удалось сохранить ответ.", "error");
              } finally {
                setBusy(false);
              }
            }}
          >
            {label}
          </button>
        ))}
        <p style={{ color: "var(--era-text-muted)" }}>За «не получилось» нет штрафов.</p>
      </div>
    );
  }

  if (checkin.status === "completed") {
    const insight = checkin.insight;
    return (
      <div className="era-page" style={{ padding: "1.2rem", display: "grid", gap: 12 }}>
        <Header title="Вот что изменилось" onBack={onBack} />
        <SegmentedRing index={checkin.index} state={checkin.state} labels={home.state_labels} dark={false} />
        <Card>
          <small>ТВОЙ ФОКУС МЕСЯЦА</small>
          <h2>{insight.focus}</h2>
          <p>{insight.insight}</p>
          <button onClick={() => setWhy(!why)}>Почему?</button>
          {why ? <p style={{ color: "var(--era-text-muted)" }}>{insight.why}</p> : null}
        </Card>
        <Card><strong>Попробуй</strong><p>{insight.experiment}</p></Card>
        {insight.experiment ? (
          <button
            className="era-btn-primary"
            onClick={async () => {
              try {
                await createDevelopmentGoal({
                  title: insight.focus || "Мой фокус",
                  experiment: insight.experiment,
                  semantic_tag: insight.semantic_tag,
                });
                await onDone();
                toast.show("Цель сохранена", "success");
              } catch {
                toast.show("Не удалось сохранить цель.", "error");
              }
            }}
          >
            Выбрать этот вариант
          </button>
        ) : null}
        <Card>
          <strong>Одна мысль себе</strong>
          <textarea rows={3} value={note} onChange={(event) => setNote(event.target.value)} style={{ width: "100%", marginTop: 8 }} />
          <button
            disabled={!note.trim()}
            onClick={async () => {
              await savePersonalNote(note, checkin.id);
              setNote("");
              toast.show("Личная заметка сохранена", "success");
            }}
          >
            Сохранить
          </button>
          <small style={{ display: "block", marginTop: 6 }}>Администратор эту заметку не видит.</small>
        </Card>
        <p style={{ color: "var(--era-text-muted)" }}>{insight.disclaimer}</p>
      </div>
    );
  }

  if (unanswered) {
    return (
      <div className="era-page" style={{ padding: "1.2rem", display: "grid", gap: 10 }}>
        <Header title="Как тебе сейчас?" onBack={onBack} />
        <Card><small>{unanswered.title}</small><h2>{unanswered.text}</h2></Card>
        {home.answer_options.map((option) => (
          <button
            key={option.value}
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                setCheckin(await saveCheckinAnswer({ [unanswered.code]: option.value }));
              } catch {
                toast.show("Ответ не сохранился.", "error");
              } finally {
                setBusy(false);
              }
            }}
          >
            {option.label}
          </button>
        ))}
        <button onClick={onBack}>Продолжить позже</button>
      </div>
    );
  }

  return (
    <div className="era-page" style={{ padding: "1.2rem", display: "grid", gap: 10 }}>
      <Header title="Контекст месяца" onBack={onBack} />
      <p>Что больше всего влияло на тебя? Выбери до 3.</p>
      <ChipGrid values={home.context_options} selected={factors} max={3} onChange={setFactors} />
      <h2>Что хочется развить?</h2>
      <ChipGrid values={home.development_wants} selected={wants} max={3} onChange={setWants} />
      <button
        className="era-btn-primary"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await saveCheckinAnswer({}, factors, wants);
            setCheckin(await completeCheckin());
            await onDone();
          } catch {
            toast.show("Не удалось завершить Check-in.", "error");
          } finally {
            setBusy(false);
          }
        }}
      >
        Получить мой результат
      </button>
    </div>
  );
}

function HistoryScreen({ labels, onBack }: { labels: DevelopmentHome["state_labels"]; onBack: () => void }) {
  const [items, setItems] = useState<VectorCheckin[] | null>(null);
  useEffect(() => {
    void fetchDevelopmentHistory().then(setItems).catch(() => setItems([]));
  }, []);
  return (
    <div className="era-page" style={{ padding: "1.2rem", display: "grid", gap: 10 }}>
      <Header title="Мой год" onBack={onBack} />
      <p>Главное сравнение здесь — ты ↔ ты.</p>
      {items === null ? (
        <SkeletonCard />
      ) : (
        items.map((item) => (
          <Card key={item.id}>
            <strong>{item.month} · {item.index}</strong>
            {DIMENSIONS.map((code) => (
              <div key={code} style={{ display: "flex", justifyContent: "space-between" }}>
                <span>{labels[code]}</span><span>{item.state[code] ?? "—"}</span>
              </div>
            ))}
          </Card>
        ))
      )}
    </div>
  );
}

function GoalsScreen({
  home,
  onRefresh,
  onBack,
}: {
  home: DevelopmentHome;
  onRefresh: () => Promise<void>;
  onBack: () => void;
}) {
  const [custom, setCustom] = useState("");
  const toast = useToast();
  return (
    <div className="era-page" style={{ padding: "1.2rem", display: "grid", gap: 10 }}>
      <Header title="Мои цели" onBack={onBack} />
      {home.current_goal ? <Card><strong>{home.current_goal.title}</strong><p>{home.current_goal.experiment}</p></Card> : null}
      <Card>
        <strong>Или придумай свой</strong>
        <textarea rows={3} value={custom} onChange={(event) => setCustom(event.target.value)} style={{ width: "100%" }} />
        <button
          disabled={!custom.trim()}
          onClick={async () => {
            await createDevelopmentGoal({ title: custom, is_custom: true });
            setCustom("");
            await onRefresh();
            toast.show("Твоя цель сохранена", "success");
          }}
        >
          Сохранить свою цель
        </button>
      </Card>
      <p>Цель — не KPI и не влияет на статус в ЭРА.</p>
    </div>
  );
}

function PrivacyScreen({ onBack }: { onBack: () => void }) {
  const [data, setData] = useState<DevelopmentPrivacy | null>(null);
  useEffect(() => {
    void fetchDevelopmentPrivacy().then(setData);
  }, []);
  if (!data) return <div className="era-page" style={{ padding: "1.2rem" }}><SkeletonCard /></div>;

  const change = async (key: "summary" | "interests" | "goals", value: boolean) => {
    const next = { ...data.admin_visibility, [key]: value };
    setData({ ...data, admin_visibility: next });
    await updateDevelopmentPrivacy(next);
  };

  return (
    <div className="era-page" style={{ padding: "1.2rem", display: "grid", gap: 10 }}>
      <Header title="Мои данные развития" onBack={onBack} />
      <Card>
        <Toggle label="Итоговый профиль" checked={data.admin_visibility.summary} onChange={(value) => void change("summary", value)} />
        <Toggle label="Интересы" checked={data.admin_visibility.interests} onChange={(value) => void change("interests", value)} />
        <Toggle label="Текущий фокус" checked={data.admin_visibility.goals} onChange={(value) => void change("goals", value)} />
      </Card>
      <Card><strong>Всегда только ты</strong><ul>{data.private_only.map((item) => <li key={item}>{item}</li>)}</ul></Card>
    </div>
  );
}

function SegmentedRing({
  index,
  state,
  labels,
  dark = true,
}: {
  index: number | null;
  state: Partial<Record<VectorDimension, number>>;
  labels: Record<VectorDimension, string>;
  dark?: boolean;
}) {
  const [selected, setSelected] = useState<VectorDimension | null>(null);
  const size = 176;
  const radius = 66;
  const circumference = 2 * Math.PI * radius;
  const gap = 9;
  const segment = circumference / 5 - gap;
  const rest = circumference - segment;
  return (
    <div style={{ display: "grid", placeItems: "center" }}>
      <div style={{ position: "relative", width: size, height: size }}>
        <svg width={size} height={size}>
          <circle cx={88} cy={88} r={radius} fill="none" stroke={dark ? "rgba(255,255,255,.14)" : "var(--era-ring-track)"} strokeWidth="13" />
          {DIMENSIONS.map((code, indexOfDimension) => (
            <circle
              key={code}
              cx={88}
              cy={88}
              r={radius}
              fill="none"
              stroke={RING_COLORS[indexOfDimension]}
              strokeWidth="13"
              strokeLinecap="round"
              strokeDasharray={`${segment} ${rest}`}
              strokeDashoffset={-(indexOfDimension * circumference / 5)}
              transform="rotate(-90 88 88)"
              opacity={0.28 + ((state[code] ?? 0) / 100) * 0.72}
              onClick={() => setSelected(code)}
            />
          ))}
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", pointerEvents: "none" }}>
          <strong style={{ fontSize: "2.5rem" }}>{index ?? "—"}</strong>
        </div>
      </div>
      {selected ? <small>{labels[selected]} · {state[selected] ?? "—"}</small> : null}
    </div>
  );
}

function ChipGrid({
  values,
  selected,
  max,
  onChange,
}: {
  values: string[];
  selected: string[];
  max: number;
  onChange: (value: string[]) => void;
}) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {values.map((value) => {
        const active = selected.includes(value);
        return (
          <button
            key={value}
            aria-pressed={active}
            onClick={() =>
              active
                ? onChange(selected.filter((item) => item !== value))
                : selected.length < max && onChange([...selected, value])
            }
          >
            {value}
          </button>
        );
      })}
    </div>
  );
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label style={{ display: "flex", justifyContent: "space-between", minHeight: 48, alignItems: "center" }}>
      <span>{label}</span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
    </label>
  );
}

function MiniAction({ title, text, onClick }: { title: string; text: string; onClick?: () => void }) {
  return <Card onClick={onClick}><strong>{title}</strong><small style={{ display: "block", marginTop: 4 }}>{text}</small></Card>;
}

function Header({ title, onBack }: { title: string; onBack?: () => void }) {
  return (
    <header style={{ display: "flex", alignItems: "center", gap: 8 }}>
      {onBack ? <button onClick={onBack}>←</button> : null}
      <h1 style={{ margin: 0 }}>{title}</h1>
    </header>
  );
}
