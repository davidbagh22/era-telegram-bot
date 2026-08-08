import { useCallback, useState } from "react";
import { describeActionError, fetchSurveys, submitSurvey } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { useAsync } from "../../hooks/useAsync";

// Surveys — the participant-facing half of
// app/handlers/participant/surveys.py. The Bot asks one question at a
// time in chat; the Mini App collects every answer in a single form and
// submits them all at once — simpler here since there's no message
// history to scroll through.
export function SurveysPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchSurveys(), [refreshKey]);
  const [openId, setOpenId] = useState<number | null>(null);
  const [drafts, setDrafts] = useState<Record<number, string[]>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const toggleOpen = useCallback(
    (surveyId: number, questionCount: number) => {
      setOpenId((current) => (current === surveyId ? null : surveyId));
      setDrafts((previous) =>
        previous[surveyId] ? previous : { ...previous, [surveyId]: Array(questionCount).fill("") },
      );
      setActionError(null);
    },
    [],
  );

  const handleAnswerChange = useCallback((surveyId: number, index: number, value: string) => {
    setDrafts((previous) => {
      const answers = [...(previous[surveyId] ?? [])];
      answers[index] = value;
      return { ...previous, [surveyId]: answers };
    });
  }, []);

  const handleSubmit = useCallback(
    async (surveyId: number) => {
      const answers = drafts[surveyId] ?? [];
      if (answers.some((answer) => !answer.trim())) {
        setActionError("Ответьте на все вопросы перед отправкой");
        return;
      }
      setBusyId(surveyId);
      setActionError(null);
      try {
        await submitSurvey(surveyId, answers);
        setOpenId(null);
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [drafts, refresh],
  );

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }
  if (state.status === "error") {
    return <EmptyState text="Не удалось загрузить опросы." />;
  }
  if (state.data.length === 0) {
    return <EmptyState text="Активных опросов пока нет." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}
      {state.data.map((survey) => {
        const isOpen = openId === survey.id;
        const answers = drafts[survey.id] ?? Array(survey.questions.length).fill("");
        return (
          <Card key={survey.id}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
              <strong>{survey.title}</strong>
              <StatusBadge
                label={survey.completed ? "пройден" : "новый"}
                tone={survey.completed ? "neutral" : "violet"}
              />
            </div>
            {survey.description && (
              <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>{survey.description}</p>
            )}
            <p style={{ margin: "0 0 0.5rem", fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>
              Вопросов: {survey.questions.length}
            </p>
            {!isOpen && (
              <button type="button" className="era-btn-primary" onClick={() => toggleOpen(survey.id, survey.questions.length)}>
                {survey.completed ? "Изменить ответы" : "Ответить"}
              </button>
            )}
            {isOpen && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
                {survey.questions.map((question, index) => (
                  <label key={index} style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                    <span style={{ fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>
                      {index + 1}. {question}
                    </span>
                    <textarea
                      rows={2}
                      value={answers[index] ?? ""}
                      onChange={(event) => handleAnswerChange(survey.id, index, event.target.value)}
                    />
                  </label>
                ))}
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button
                    type="button"
                    className="era-btn-primary"
                    disabled={busyId === survey.id}
                    onClick={() => handleSubmit(survey.id)}
                  >
                    Отправить
                  </button>
                  <button type="button" onClick={() => setOpenId(null)}>
                    Отмена
                  </button>
                </div>
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
