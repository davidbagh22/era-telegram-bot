import { useEffect, useMemo, useState } from "react";

import {
  completeAssessment,
  fetchAssessment,
  fetchAssessments,
  saveAssessmentAnswer,
  startAssessment,
} from "../api/development";
import { Card } from "../components/Card";
import { SkeletonCard } from "../components/Skeleton";
import { useToast } from "../components/Toast";
import type {
  AssessmentCard,
  AssessmentResult,
  AssessmentSession,
} from "../types/development";

interface AssessmentExperienceProps {
  onBack: () => void;
}

export function AssessmentExperience({ onBack }: AssessmentExperienceProps) {
  const [items, setItems] = useState<AssessmentCard[] | null>(null);
  const [selected, setSelected] = useState<AssessmentCard | null>(null);
  const [runner, setRunner] = useState<AssessmentSession | null>(null);
  const [result, setResult] = useState<AssessmentResult | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  async function reloadList() {
    try {
      setItems(await fetchAssessments());
    } catch {
      setItems([]);
    }
  }

  useEffect(() => {
    void reloadList();
  }, []);

  async function openAssessment(item: AssessmentCard) {
    setBusy(true);
    try {
      const detail = await fetchAssessment(item.code);
      setSelected(detail);
      setResult(detail.last_result ?? null);
      setRunner(null);
    } catch {
      toast.show("Не удалось открыть исследование.", "error");
    } finally {
      setBusy(false);
    }
  }

  async function begin() {
    if (!selected) return;
    setBusy(true);
    try {
      setResult(null);
      setRunner(await startAssessment(selected.code));
    } catch (error) {
      const message = error instanceof Error ? error.message : "assessment_start_failed";
      if (message === "assessment_age_restricted") {
        toast.show("Это исследование пока недоступно для твоего возраста.", "error");
      } else if (message === "assessment_is_derived") {
        toast.show("Этот раздел собирается автоматически из других результатов.", "error");
      } else {
        toast.show("Не удалось начать исследование.", "error");
      }
    } finally {
      setBusy(false);
    }
  }

  async function answer(questionCode: string, value: number) {
    if (!runner) return;
    setBusy(true);
    try {
      setRunner(await saveAssessmentAnswer(runner.id, questionCode, value));
    } catch {
      toast.show("Ответ не сохранился. Попробуй ещё раз.", "error");
    } finally {
      setBusy(false);
    }
  }

  async function finalizeAssessment() {
    if (!runner) return;
    setBusy(true);
    try {
      const completed = await completeAssessment(runner.id);
      setResult(completed);
      setRunner(null);
      await reloadList();
    } catch {
      toast.show("Не удалось завершить исследование. Проверь ответы и попробуй ещё раз.", "error");
    } finally {
      setBusy(false);
    }
  }

  if (runner) {
    return (
      <AssessmentRunner
        session={runner}
        busy={busy}
        onAnswer={answer}
        onComplete={finalizeAssessment}
        onBack={() => setRunner(null)}
      />
    );
  }

  if (selected) {
    return (
      <AssessmentDetail
        item={selected}
        result={result}
        busy={busy}
        onStart={begin}
        onBack={() => {
          setSelected(null);
          setResult(null);
        }}
      />
    );
  }

  return (
    <div className="era-page" style={{ padding: "1.2rem", display: "grid", gap: 10 }}>
      <Header title="Все исследования" onBack={onBack} />
      <p style={{ marginTop: 0, color: "var(--era-text-muted)" }}>
        Не нужно проходить всё сразу. Выбирай то, что сейчас действительно хочется понять о себе.
      </p>
      {items === null ? (
        <>
          <SkeletonCard />
          <SkeletonCard />
        </>
      ) : items.length === 0 ? (
        <Card>
          <strong>Исследования временно недоступны</strong>
          <p>Попробуй открыть раздел ещё раз.</p>
        </Card>
      ) : (
        items.map((item) => (
          <Card key={item.code} onClick={busy ? undefined : () => void openAssessment(item)}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <strong>{item.title}</strong>
              {item.last_result ? <span aria-label="Пройдено">✓</span> : null}
            </div>
            <p style={{ color: "var(--era-text-muted)" }}>{item.description}</p>
            <small>
              {item.estimated_minutes > 0 ? `≈ ${item.estimated_minutes} мин` : "Собирается автоматически"}
              {item.question_count ? ` · ${item.question_count} вопросов` : ""}
            </small>
          </Card>
        ))
      )}
    </div>
  );
}

function AssessmentDetail({
  item,
  result,
  busy,
  onStart,
  onBack,
}: {
  item: AssessmentCard;
  result: AssessmentResult | null;
  busy: boolean;
  onStart: () => void;
  onBack: () => void;
}) {
  const isDerived = item.construct_type === "derived";
  return (
    <div className="era-page" style={{ padding: "1.2rem", display: "grid", gap: 10 }}>
      <Header title={item.title} onBack={onBack} />
      <Card>
        <strong>Что покажет</strong>
        <p>{item.description}</p>
        <strong>Методика</strong>
        <p>{item.methodology}</p>
        <small style={{ color: "var(--era-text-muted)" }}>
          Источник: {item.source}
          {item.version ? ` · версия ${item.version}` : ""}
        </small>
      </Card>

      {item.validation_note ? (
        <Card>
          <strong>О точности</strong>
          <p>{item.validation_note}</p>
        </Card>
      ) : null}

      {item.notice ? (
        <p style={{ color: "var(--era-text-muted)", margin: 0 }}>{item.notice}</p>
      ) : null}

      {isDerived ? (
        <Card>
          <strong>{item.strengths?.length ? "Что уже видно" : "Нужно немного данных"}</strong>
          {item.strengths?.length ? (
            <ul>
              {item.strengths.map((strength) => (
                <li key={strength}>{strength}</li>
              ))}
            </ul>
          ) : (
            <p>Пройди базовые исследования — после этого здесь появится аккуратный синтез выраженных сторон.</p>
          )}
          {item.interest_code?.length ? <p>Код интересов: {item.interest_code.join("–")}</p> : null}
        </Card>
      ) : (
        <>
          {result ? <AssessmentResultCard result={result} /> : null}
          <button className="era-btn-primary" disabled={!item.available || busy} onClick={onStart}>
            {result ? "Пройти ещё раз" : "Начать"}
          </button>
          <small style={{ color: "var(--era-text-muted)" }}>
            {item.question_count ?? "—"} вопросов · примерно {item.estimated_minutes} мин · ответы сохраняются сразу
          </small>
        </>
      )}

      <Card>
        <strong>Что будет с результатами</strong>
        <p style={{ marginBottom: 0 }}>
          Ты видишь полный результат. Команда ЭРА получает только те итоговые показатели развития, которыми ты разрешил делиться. Сырые ответы и личные заметки не используются для рейтинга, отбора в проекты или назначения ролей.
        </p>
      </Card>
    </div>
  );
}

function AssessmentRunner({
  session,
  busy,
  onAnswer,
  onComplete,
  onBack,
}: {
  session: AssessmentSession;
  busy: boolean;
  onAnswer: (questionCode: string, value: number) => Promise<void>;
  onComplete: () => Promise<void>;
  onBack: () => void;
}) {
  const firstUnanswered = useMemo(() => {
    const index = session.questions.findIndex((question) => session.answers[question.code] === undefined);
    return index === -1 ? Math.max(0, session.questions.length - 1) : index;
  }, [session.questions, session.answers]);
  const [cursor, setCursor] = useState(firstUnanswered);
  const [reviewing, setReviewing] = useState(session.answered_count === session.question_count);

  useEffect(() => {
    if (session.answered_count === session.question_count) setReviewing(true);
  }, [session.answered_count, session.question_count]);

  useEffect(() => {
    if (cursor >= session.questions.length) setCursor(Math.max(0, session.questions.length - 1));
  }, [cursor, session.questions.length]);

  const current = session.questions[cursor];
  const progress = session.question_count
    ? Math.round((session.answered_count / session.question_count) * 100)
    : 0;

  if (!current) {
    return (
      <div className="era-page" style={{ padding: "1.2rem" }}>
        <SkeletonCard />
      </div>
    );
  }

  if (reviewing) {
    return (
      <div className="era-page" style={{ padding: "1.2rem", display: "grid", gap: 12 }}>
        <Header title={session.title} onBack={onBack} />
        <Card gradient>
          <small>ГОТОВО К РЕЗУЛЬТАТУ</small>
          <h2 style={{ marginBottom: 6 }}>Все ответы сохранены</h2>
          <p style={{ margin: 0, color: "rgba(255,255,255,.78)" }}>
            До отправки можно вернуться и изменить любой ответ. После завершения эта сессия останется отдельной записью в истории.
          </p>
        </Card>
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            setCursor(Math.max(0, session.questions.length - 1));
            setReviewing(false);
          }}
        >
          ← Проверить последний ответ
        </button>
        <button className="era-btn-primary" disabled={busy} onClick={() => void onComplete()}>
          {busy ? "Сохраняем…" : "Получить результат"}
        </button>
        <button disabled={busy} onClick={onBack}>Продолжить позже</button>
      </div>
    );
  }

  const selectedValue = session.answers[current.code];
  return (
    <div className="era-page" style={{ padding: "1.2rem", display: "grid", gap: 10 }}>
      <Header title={session.title} onBack={onBack} />
      <div aria-label={`Прогресс ${progress}%`} style={{ display: "grid", gap: 6 }}>
        <div
          style={{
            height: 6,
            borderRadius: 999,
            background: "var(--era-ring-track)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${progress}%`,
              height: "100%",
              background: "var(--era-red)",
              transition: "width .2s ease",
            }}
          />
        </div>
        <small style={{ color: "var(--era-text-muted)" }}>
          {cursor + 1} из {session.question_count} · ещё около {Math.max(1, Math.ceil((session.question_count - session.answered_count) * 0.12))} мин
        </small>
      </div>

      <Card>
        <h2 style={{ margin: 0 }}>{current.text}</h2>
      </Card>

      <div style={{ display: "grid", gap: 8 }}>
        {current.options.map((option) => (
          <button
            key={option.value}
            disabled={busy}
            aria-pressed={selectedValue === option.value}
            style={{
              minHeight: 52,
              textAlign: "left",
              borderColor: selectedValue === option.value ? "var(--era-red)" : undefined,
            }}
            onClick={async () => {
              await onAnswer(current.code, option.value);
              if (cursor < session.questions.length - 1) setCursor(cursor + 1);
            }}
          >
            {option.label}
          </button>
        ))}
      </div>

      {cursor > 0 ? (
        <button disabled={busy} onClick={() => setCursor(cursor - 1)}>← Предыдущий вопрос</button>
      ) : null}
      <button disabled={busy} onClick={onBack}>Продолжить позже</button>
      <small style={{ color: "var(--era-text-muted)" }}>
        Каждый ответ сохраняется сразу. Можно выйти и вернуться позже без потери данных.
      </small>
    </div>
  );
}

function AssessmentResultCard({ result }: { result: AssessmentResult }) {
  const entries = Object.entries(result.scores);
  return (
    <>
      <Card gradient>
        <small>ТВОЙ РЕЗУЛЬТАТ</small>
        <h2>{result.interpretation?.title ?? result.title}</h2>
        <p>{result.interpretation?.summary}</p>
      </Card>
      {entries.length > 1 ? (
        <Card>
          <strong>Твоя карта</strong>
          <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
            {entries.map(([scale, score]) => (
              <div key={scale} style={{ display: "grid", gap: 3 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                  <span>{prettyScale(scale)}</span>
                  <strong>{Math.round(score.normalized)}</strong>
                </div>
                <div style={{ height: 5, borderRadius: 999, background: "var(--era-ring-track)" }}>
                  <div
                    style={{
                      width: `${Math.max(0, Math.min(100, score.normalized))}%`,
                      height: "100%",
                      borderRadius: 999,
                      background: "var(--era-red)",
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Card>
      ) : null}
      <p style={{ color: "var(--era-text-muted)" }}>
        {result.interpretation?.note ?? result.notice}
      </p>
    </>
  );
}

function prettyScale(scale: string): string {
  const labels: Record<string, string> = {
    wellbeing: "Самочувствие",
    self_efficacy: "Самоэффективность",
    extraversion: "Проявленность",
    agreeableness: "Взаимодействие",
    conscientiousness: "Организованность",
    emotional_stability: "Устойчивость",
    intellect: "Идеи и воображение",
    R: "Практическое",
    I: "Исследовательское",
    A: "Творческое",
    S: "Социальное",
    E: "Предпринимательское",
    C: "Организационное",
    autonomy: "Самостоятельность",
    competence: "Компетентность",
    relatedness: "Связь с людьми",
  };
  return labels[scale] ?? scale;
}

function Header({ title, onBack }: { title: string; onBack: () => void }) {
  return (
    <header style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <button onClick={onBack} aria-label="Назад">←</button>
      <h1 style={{ margin: 0 }}>{title}</h1>
    </header>
  );
}
