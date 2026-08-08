import { useCallback, useState } from "react";
import {
  archiveSurvey,
  createSurvey,
  describeActionError,
  fetchAdminSurveys,
  fetchSurveyResponses,
  getOrCreateMonthlySurvey,
  sendSurvey,
  updateSurvey,
} from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { useAsync } from "../../hooks/useAsync";
import type { SurveyAdmin, SurveyResponseAdmin } from "../../types/admin";

const inputStyle = {
  width: "100%",
  fontFamily: "var(--era-font-body)",
  padding: "0.5rem",
  borderRadius: "0.5rem",
  border: "1px solid var(--era-border)",
  background: "var(--era-bg)",
  color: "var(--era-text)",
} as const;

const STATUS_LABELS: Record<string, string> = {
  draft: "черновик",
  active: "активен",
  sent: "отправлен",
  archived: "архив",
};

function questionsToText(questions: string[]): string {
  return questions.join("\n");
}

function textToQuestions(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

// "Опросы" — the Mini App equivalent of the admin half of
// app/handlers/admin/surveys_analytics.py (create/edit/send/archive a
// survey, view responses). Excel export of results is not ported yet —
// it remains a Bot-only capability for now.
export function AdminSurveysScreen() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAdminSurveys(), [refreshKey]);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [questionsText, setQuestionsText] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [responsesFor, setResponsesFor] = useState<SurveyAdmin | null>(null);
  const [responses, setResponses] = useState<SurveyResponseAdmin[]>([]);
  const [loadingResponses, setLoadingResponses] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const resetForm = useCallback(() => {
    setTitle("");
    setDescription("");
    setQuestionsText("");
    setEditingId(null);
  }, []);

  const startEditing = useCallback((survey: SurveyAdmin) => {
    setEditingId(survey.id);
    setTitle(survey.title);
    setDescription(survey.description ?? "");
    setQuestionsText(questionsToText(survey.questions));
    setActionError(null);
  }, []);

  const handleSave = useCallback(async () => {
    const questions = textToQuestions(questionsText);
    if (!title.trim() || questions.length === 0) return;
    setCreating(true);
    setActionError(null);
    try {
      if (editingId != null) {
        await updateSurvey(editingId, { title: title.trim(), description: description.trim() || null, questions });
      } else {
        await createSurvey({ title: title.trim(), description: description.trim() || null, questions });
      }
      resetForm();
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setCreating(false);
    }
  }, [title, description, questionsText, editingId, resetForm, refresh]);

  const handleMonthlyTemplate = useCallback(async () => {
    setCreating(true);
    setActionError(null);
    try {
      await getOrCreateMonthlySurvey();
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setCreating(false);
    }
  }, [refresh]);

  const runAction = useCallback(
    async (surveyId: number, action: () => Promise<unknown>) => {
      setBusyId(surveyId);
      setActionError(null);
      try {
        await action();
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [refresh],
  );

  const openResponses = useCallback(async (survey: SurveyAdmin) => {
    setResponsesFor(survey);
    setLoadingResponses(true);
    setActionError(null);
    try {
      setResponses(await fetchSurveyResponses(survey.id));
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setLoadingResponses(false);
    }
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}

      <Card>
        <strong>{editingId != null ? "Редактирование опроса" : "Новый опрос"}</strong>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
          <input placeholder="Название" value={title} onChange={(e) => setTitle(e.target.value)} style={inputStyle} />
          <textarea
            placeholder="Описание (необязательно)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            style={inputStyle}
          />
          <textarea
            placeholder={"Вопросы, каждый на новой строке"}
            value={questionsText}
            onChange={(e) => setQuestionsText(e.target.value)}
            rows={4}
            style={inputStyle}
          />
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              type="button"
              className="era-btn-primary"
              disabled={creating || !title.trim() || textToQuestions(questionsText).length === 0}
              onClick={handleSave}
            >
              {editingId != null ? "Сохранить" : "Создать опрос"}
            </button>
            {editingId != null && (
              <button type="button" onClick={resetForm}>
                Отмена
              </button>
            )}
            {editingId == null && (
              <button type="button" disabled={creating} onClick={handleMonthlyTemplate}>
                Ежемесячный шаблон
              </button>
            )}
          </div>
        </div>
      </Card>

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить опросы." />}
      {state.status === "ready" && state.data.length === 0 && <EmptyState text="Опросов пока нет." />}
      {state.status === "ready" &&
        state.data.map((survey) => (
          <Card key={survey.id}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
              <strong>{survey.title}</strong>
              <StatusBadge label={STATUS_LABELS[survey.status] ?? survey.status} tone="violet" />
            </div>
            {survey.description && (
              <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>{survey.description}</p>
            )}
            <p style={{ margin: "0 0 0.5rem", fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>
              {survey.is_monthly ? "Ежемесячный · " : ""}
              Вопросов: {survey.questions.length} · Ответов: {survey.response_count}
              {survey.sent_at ? ` · Отправлен: ${survey.sent_at.slice(0, 10)}` : ""}
            </p>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              {survey.status !== "archived" && (
                <button type="button" disabled={busyId === survey.id} onClick={() => startEditing(survey)}>
                  Редактировать
                </button>
              )}
              {survey.status !== "archived" && (
                <button
                  type="button"
                  className="era-btn-primary"
                  disabled={busyId === survey.id}
                  onClick={() => runAction(survey.id, () => sendSurvey(survey.id))}
                >
                  Отправить
                </button>
              )}
              <button type="button" disabled={loadingResponses} onClick={() => openResponses(survey)}>
                Ответы ({survey.response_count})
              </button>
              {survey.status !== "archived" && (
                <button
                  type="button"
                  disabled={busyId === survey.id}
                  onClick={() => runAction(survey.id, () => archiveSurvey(survey.id))}
                >
                  Архивировать
                </button>
              )}
            </div>

            {responsesFor?.id === survey.id && (
              <div style={{ marginTop: "0.75rem", borderTop: "1px solid var(--era-border)", paddingTop: "0.5rem" }}>
                {loadingResponses && <p style={{ color: "var(--era-text-muted)" }}>Загрузка ответов…</p>}
                {!loadingResponses && responses.length === 0 && (
                  <p style={{ color: "var(--era-text-muted)", margin: 0 }}>Ответов пока нет.</p>
                )}
                {!loadingResponses &&
                  responses.map((response) => (
                    <div key={response.user_id} style={{ marginBottom: "0.5rem" }}>
                      <strong style={{ fontSize: "0.875rem" }}>{response.user_name}</strong>
                      {response.answers.map((answer, index) => (
                        <p key={index} style={{ margin: "0.125rem 0", fontSize: "0.8125rem" }}>
                          <span style={{ color: "var(--era-text-muted)" }}>{answer.question}:</span> {answer.answer}
                        </p>
                      ))}
                    </div>
                  ))}
                <button type="button" onClick={() => setResponsesFor(null)}>
                  Закрыть
                </button>
              </div>
            )}
          </Card>
        ))}
    </div>
  );
}
