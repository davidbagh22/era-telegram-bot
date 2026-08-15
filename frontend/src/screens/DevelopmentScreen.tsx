import { useEffect, useMemo, useState } from "react";

import {
  acceptDevelopmentConsent,
  completeCheckin,
  createDevelopmentGoal,
  fetchCurrentCheckin,
  fetchDevelopmentHistory,
  fetchDevelopmentHome,
  fetchDevelopmentPrivacy,
  fetchPersonalInsights,
  fetchRememberedNotes,
  reviewDevelopmentGoal,
  saveCheckinAnswer,
  savePersonalNote,
  submitInsightFeedback,
  updateDevelopmentPrivacy,
} from "../api/development";
import { Card } from "../components/Card";
import { SkeletonCard } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import { useToast } from "../components/Toast";
import type {
  DevelopmentHome,
  DevelopmentPrivacy,
  PersonalInsightItem,
  RememberedNote,
  VectorCheckin,
  VectorDimension,
} from "../types/development";
import { AssessmentExperience } from "./AssessmentExperience";

export type DevelopmentRoute = "home" | "checkin" | "assessments" | "history" | "goals" | "privacy";

const DIMENSIONS: VectorDimension[] = ["energy", "agency", "autonomy", "connection", "direction"];
const RING_COLORS = ["var(--era-red)", "#8f1e2e", "var(--era-gold-ink)", "#4b4a50", "#c9c5bf"];
const GOAL_OBSTACLES = [
  "не хватило времени",
  "не было подходящей ситуации",
  "стало неинтересно",
  "было страшно/неловко",
  "забыл",
  "выбрал другое",
  "не знаю",
];

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
        <small>{home.current_checkin?.theme ? home.current_checkin.theme.toUpperCase() : "ТВОЙ CHECK-IN"}</small>
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
        <MiniAction title="Мой год" text="Динамика, открытия и память" onClick={() => onNavigate?.("history")} />
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
        <p>Видит только разрешённые итоговые показатели и динамику — чтобы лучше понимать потребности сообщества.</p>
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
  const initialCursor = useMemo(() => {
    const index = home.questions.findIndex((question) => home.current_checkin?.answers?.[question.code] === undefined);
    return index === -1 ? Math.max(0, home.questions.length - 1) : index;
  }, [home.current_checkin, home.questions]);
  const [cursor, setCursor] = useState(initialCursor);
  const [reviewQuestions, setReviewQuestions] = useState(false);
  const [busy, setBusy] = useState(false);
  const [factors, setFactors] = useState<string[]>(home.current_checkin?.context.factors ?? []);
  const [wants, setWants] = useState<string[]>(home.current_checkin?.context.development_wants ?? []);
  const [why, setWhy] = useState(false);
  const [note, setNote] = useState("");
  const [goalReviewed, setGoalReviewed] = useState(Boolean(home.current_goal?.review));
  const [pendingGoalResult, setPendingGoalResult] = useState<string | null>(null);

  useEffect(() => {
    if (!checkin) {
      void fetchCurrentCheckin().then(setCheckin).catch(() => toast.show("Не удалось загрузить Check-in.", "error"));
    }
  }, [checkin, toast]);

  if (!checkin) return <div className="era-page" style={{ padding: "1.2rem" }}><SkeletonCard /></div>;

  if (home.current_goal && home.current_goal.month < checkin.month && !goalReviewed && checkin.status !== "completed") {
    if (pendingGoalResult === "not_done") {
      return (
        <div className="era-page" style={{ padding: "1.2rem", display: "grid", gap: 10 }}>
          <Header title="Что помешало больше всего?" onBack={() => setPendingGoalResult(null)} />
          <p style={{ margin: 0, color: "var(--era-text-muted)" }}>Это не оценка дисциплины. Ответ поможет не предложить в следующем месяце ту же неподходящую цель.</p>
          {GOAL_OBSTACLES.map((obstacle) => (
            <button
              key={obstacle}
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await reviewDevelopmentGoal(home.current_goal!.id, "not_done", obstacle);
                  setGoalReviewed(true);
                  setPendingGoalResult(null);
                } catch {
                  toast.show("Не удалось сохранить ответ.", "error");
                } finally {
                  setBusy(false);
                }
              }}
            >
              {obstacle}
            </button>
          ))}
        </div>
      );
    }

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
              if (value === "not_done") {
                setPendingGoalResult(value);
                return;
              }
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
          <small>ГЛАВНОЕ СЕЙЧАС</small>
          {insight.support ? <p><strong>Опора.</strong> {insight.support}</p> : null}
          {insight.tension ? <p><strong>Напряжение.</strong> {insight.tension}</p> : null}
          {insight.change ? <p><strong>Что изменилось.</strong> {insight.change}</p> : null}
        </Card>
        <Card style={{ borderLeft: "3px solid var(--era-red)" }}>
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
              try {
                await savePersonalNote(note, checkin.id);
                setNote("");
                toast.show("Личная заметка сохранена", "success");
              } catch {
                toast.show("Не удалось сохранить заметку.", "error");
              }
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

  const allAnswered = home.questions.every((question) => checkin.answers?.[question.code] !== undefined);
  const currentQuestion = home.questions[cursor];
  const showQuestion = currentQuestion && (!allAnswered || reviewQuestions);
  const answeredCount = home.questions.filter((question) => checkin.answers?.[question.code] !== undefined).length;
  const progress = home.questions.length ? Math.round((answeredCount / home.questions.length) * 100) : 0;

  if (showQuestion) {
    const selectedValue = checkin.answers[currentQuestion.code];
    return (
      <div className="era-page" style={{ padding: "1.2rem", display: "grid", gap: 10 }}>
        <Header title={checkin.theme ? `Check-in · ${checkin.theme}` : "Как тебе сейчас?"} onBack={onBack} />
        <div aria-label={`Прогресс ${progress}%`} style={{ display: "grid", gap: 5 }}>
          <div style={{ height: 6, borderRadius: 999, background: "var(--era-ring-track)", overflow: "hidden" }}>
            <div style={{ width: `${progress}%`, height: "100%", background: "var(--era-red)", transition: "width .2s ease" }} />
          </div>
          <small style={{ color: "var(--era-text-muted)" }}>{answeredCount} из {home.questions.length} · ещё около {Math.max(1, Math.ceil((home.questions.length - answeredCount) * .6))} мин</small>
        </div>
        <Card><small>{currentQuestion.title}</small><h2>{currentQuestion.text}</h2></Card>
        {home.answer_options.map((option) => (
          <button
            key={option.value}
            disabled={busy}
            aria-pressed={selectedValue === option.value}
            style={{ borderColor: selectedValue === option.value ? "var(--era-red)" : undefined }}
            onClick={async () => {
              setBusy(true);
              try {
                const saved = await saveCheckinAnswer({ [currentQuestion.code]: option.value });
                setCheckin(saved);
                if (cursor < home.questions.length - 1) {
                  setCursor(cursor + 1);
                } else {
                  setReviewQuestions(false);
                }
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
        {selectedValue !== undefined && cursor < home.questions.length - 1 ? (
          <button disabled={busy} onClick={() => setCursor(cursor + 1)}>Далее →</button>
        ) : null}
        {cursor > 0 ? <button disabled={busy} onClick={() => setCursor(cursor - 1)}>← Предыдущий вопрос</button> : null}
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
        type="button"
        onClick={() => {
          setCursor(Math.max(0, home.questions.length - 1));
          setReviewQuestions(true);
        }}
      >
        ← Проверить ответы
      </button>
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
            toast.show("Не удалось завершить Check-in. Проверь, что все ответы сохранены.", "error");
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
  const [insights, setInsights] = useState<PersonalInsightItem[]>([]);
  const [notes, setNotes] = useState<RememberedNote[]>([]);
  const toast = useToast();

  useEffect(() => {
    void Promise.all([
      fetchDevelopmentHistory(),
      fetchPersonalInsights(),
      fetchRememberedNotes(),
    ]).then(([history, discoveries, memories]) => {
      setItems(history);
      setInsights(discoveries);
      setNotes(memories);
    }).catch(() => setItems([]));
  }, []);

  const annual = items && items.length ? buildYearStory(items, labels) : null;

  return (
    <div className="era-page" style={{ padding: "1.2rem", display: "grid", gap: 10 }}>
      <Header title="Мой год" onBack={onBack} />
      <p style={{ marginTop: 0, color: "var(--era-text-muted)" }}>Главное сравнение здесь — ты ↔ ты. Чем длиннее история, тем полезнее становятся наблюдения.</p>
      {items === null ? (
        <SkeletonCard />
      ) : items.length === 0 ? (
        <Card><strong>История начнётся после первого Check-in</strong><p style={{ marginBottom: 0 }}>Здесь не будет сравнения с другими людьми.</p></Card>
      ) : (
        <>
          {annual ? (
            <Card gradient>
              <small>ТВОЙ ГОД</small>
              <h2 style={{ marginBottom: 8 }}>{annual.title}</h2>
              <p>{annual.started}</p>
              <p>{annual.changed}</p>
              <p style={{ marginBottom: 0 }}>{annual.next}</p>
            </Card>
          ) : null}

          {notes.length ? (
            <Card style={{ borderLeft: "3px solid var(--era-gold-ink)" }}>
              <small>ТЫ ПИСАЛ СЕБЕ РАНЬШЕ</small>
              <p style={{ fontSize: "1.05rem" }}>«{notes[0].text}»</p>
              <small style={{ color: "var(--era-text-muted)" }}>{new Date(notes[0].created_at).toLocaleDateString("ru-RU")}</small>
            </Card>
          ) : null}

          {insights.length ? (
            <section style={{ display: "grid", gap: 8 }}>
              <h2 style={{ marginBottom: 0 }}>Мои открытия</h2>
              {insights.slice(0, 8).map((insight) => (
                <Card key={insight.id}>
                  <p style={{ marginTop: 0 }}>{insight.text}</p>
                  {insight.accepted === null ? (
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 6 }}>
                      <button
                        onClick={async () => {
                          try {
                            await submitInsightFeedback(insight.id, true);
                            setInsights((current) => current.map((item) => item.id === insight.id ? { ...item, accepted: true } : item));
                            toast.show("Открытие закреплено", "success");
                          } catch {
                            toast.show("Не удалось сохранить выбор.", "error");
                          }
                        }}
                      >Это про меня</button>
                      <button
                        onClick={async () => {
                          try {
                            await submitInsightFeedback(insight.id, false);
                            setInsights((current) => current.filter((item) => item.id !== insight.id));
                          } catch {
                            toast.show("Не удалось сохранить выбор.", "error");
                          }
                        }}
                      >Не похоже на меня</button>
                    </div>
                  ) : insight.accepted ? <small>Закреплено как твоё наблюдение</small> : null}
                </Card>
              ))}
            </section>
          ) : null}

          <section style={{ display: "grid", gap: 8 }}>
            <h2 style={{ marginBottom: 0 }}>Динамика</h2>
            {items.map((item) => (
              <Card key={item.id}>
                <strong>{item.month} · {item.index ?? "—"}</strong>
                {item.theme ? <small style={{ display: "block", margin: "3px 0 6px", color: "var(--era-text-muted)" }}>{item.theme}</small> : null}
                {DIMENSIONS.map((code) => (
                  <div key={code} style={{ display: "flex", justifyContent: "space-between" }}>
                    <span>{labels[code]}</span><span>{item.state[code] ?? "—"}</span>
                  </div>
                ))}
              </Card>
            ))}
          </section>
        </>
      )}
    </div>
  );
}

function buildYearStory(items: VectorCheckin[], labels: DevelopmentHome["state_labels"]) {
  const chronological = [...items].reverse();
  const first = chronological[0];
  const latest = chronological[chronological.length - 1];
  const changes = DIMENSIONS.map((code) => ({ code, delta: (latest.state[code] ?? 0) - (first.state[code] ?? 0) }));
  const strongest = [...changes].sort((a, b) => b.delta - a.delta)[0];
  const mostChanged = [...changes].sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))[0];
  const nextCode = DIMENSIONS.reduce((lowest, code) => (latest.state[code] ?? 101) < (latest.state[lowest] ?? 101) ? code : lowest, DIMENSIONS[0]);
  return {
    title: `${chronological.length} ${chronological.length === 1 ? "точка" : "точек"} твоей истории`,
    started: `В начале этой истории твой снимок состояния был ${first.index ?? "—"}. Сейчас — ${latest.index ?? "—"}.`,
    changed: strongest.delta > 0
      ? `Сильнее всего выросла область «${labels[strongest.code]}»: +${strongest.delta}. Самое заметное изменение в целом — «${labels[mostChanged.code]}».`
      : `История пока не показывает устойчивого роста одной области — и это нормально: здесь важнее заметить реальную динамику, а не улучшать цифру любой ценой.`,
    next: `Твой следующий вектор наблюдения сейчас — «${labels[nextCode]}». Это не слабость, а область, которую полезно продолжить замечать.`,
  };
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
        <textarea rows={3} value={custom} onChange={(event) => setCustom(event.target.value)} style={{ width: "100%" }} placeholder="В этом месяце я хочу…" />
        <button
          disabled={!custom.trim()}
          onClick={async () => {
            try {
              await createDevelopmentGoal({ title: custom, is_custom: true });
              setCustom("");
              await onRefresh();
              toast.show("Твоя цель сохранена", "success");
            } catch {
              toast.show("Не удалось сохранить цель.", "error");
            }
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
  const toast = useToast();
  useEffect(() => {
    void fetchDevelopmentPrivacy().then(setData);
  }, []);
  if (!data) return <div className="era-page" style={{ padding: "1.2rem" }}><SkeletonCard /></div>;

  const change = async (key: "summary" | "interests" | "goals", value: boolean) => {
    const previous = data.admin_visibility;
    const next = { ...previous, [key]: value };
    setData({ ...data, admin_visibility: next });
    try {
      await updateDevelopmentPrivacy(next);
    } catch {
      setData({ ...data, admin_visibility: previous });
      toast.show("Не удалось изменить настройку.", "error");
    }
  };

  return (
    <div className="era-page" style={{ padding: "1.2rem", display: "grid", gap: 10 }}>
      <Header title="Мои данные развития" onBack={onBack} />
      <Card>
        <Toggle label="Итоговый профиль" checked={data.admin_visibility.summary} onChange={(value) => void change("summary", value)} />
        <Toggle label="Интересы" checked={data.admin_visibility.interests} onChange={(value) => void change("interests", value)} />
        <Toggle label="Текущий фокус" checked={data.admin_visibility.goals} onChange={(value) => void change("goals", value)} />
      </Card>
      <Card><strong>Команда ЭРА может видеть</strong><ul>{data.admin_can_see.map((item) => <li key={item}>{item}</li>)}</ul></Card>
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
        <svg width={size} height={size} role="img" aria-label={`Мой вектор сейчас: ${index ?? "нет данных"}`}>
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
              aria-label={`${labels[code]} ${state[code] ?? "нет данных"}`}
            />
          ))}
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", pointerEvents: "none" }}>
          <div style={{ textAlign: "center" }}><strong style={{ display: "block", fontSize: "2.5rem" }}>{index ?? "—"}</strong><small>Сейчас</small></div>
        </div>
      </div>
      {selected ? <small>{labels[selected]} · {state[selected] ?? "—"}</small> : <small>Нажми на сегмент, чтобы увидеть область</small>}
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
      {onBack ? <button onClick={onBack} aria-label="Назад">←</button> : null}
      <h1 style={{ margin: 0 }}>{title}</h1>
    </header>
  );
}
