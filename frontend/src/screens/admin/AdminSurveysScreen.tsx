import { useCallback, useMemo, useState } from "react";
import {
  archiveSurvey,
  createSurvey,
  describeActionError,
  fetchAdminSurveys,
  fetchSurveyResponses,
  getOrCreateMonthlySurvey,
  sendChatBroadcast,
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

const CONFERENCE_TITLE = "Кого ты хочешь услышать на молодёжной конференции ЭРА?";
const CONFERENCE_MARKER = "__ERA_CONFERENCE_SPEAKERS__";
const CONFERENCE_CHAT_TEXT = `🔥 Кого ты реально хочешь услышать вживую?

Мы собираем программу молодёжной конференции ЭРА — и хотим решить её вместе с вами.

Внутри один список потенциальных спикеров. Выбери до 7 человек — тех, ради встречи с кем ты действительно пришёл бы.

Не нашёл нужного человека? В конце можно вписать своего кандидата.

Именно по результатам этого голосования будем собирать программу конференции.

[[era-survey]]`;

function questionsToText(questions: string[]): string {
  return questions.join("\n");
}

function textToQuestions(text: string): string[] {
  return text.split("\n").map((line) => line.trim()).filter(Boolean);
}

function isConferenceSurvey(survey: SurveyAdmin): boolean {
  return survey.title === CONFERENCE_TITLE;
}

function parseChoices(answer: string): string[] {
  try {
    const parsed = JSON.parse(answer);
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function displayAnswer(answer: string): string {
  const choices = parseChoices(answer);
  return choices.length > 0 ? choices.join(", ") : answer || "—";
}

function buildRanking(responses: SurveyResponseAdmin[]): { name: string; votes: number; percent: number }[] {
  const counts = new Map<string, number>();
  for (const response of responses) {
    const choices = parseChoices(response.answers[0]?.answer ?? "");
    for (const choice of new Set(choices)) counts.set(choice, (counts.get(choice) ?? 0) + 1);
  }
  const total = responses.length || 1;
  return [...counts.entries()]
    .map(([name, votes]) => ({ name, votes, percent: Math.round((votes / total) * 100) }))
    .sort((a, b) => b.votes - a.votes || a.name.localeCompare(b.name, "ru"));
}

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
  const ranking = useMemo(
    () => responsesFor && isConferenceSurvey(responsesFor) ? buildRanking(responses) : [],
    [responsesFor, responses],
  );
  const customSuggestions = useMemo(
    () => responsesFor && isConferenceSurvey(responsesFor)
      ? responses.map((response) => response.answers[1]?.answer?.trim()).filter((answer): answer is string => Boolean(answer))
      : [],
    [responsesFor, responses],
  );

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
      if (editingId != null) await updateSurvey(editingId, { title: title.trim(), description: description.trim() || null, questions });
      else await createSurvey({ title: title.trim(), description: description.trim() || null, questions });
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

  const handleConferenceTemplate = useCallback(async () => {
    setCreating(true);
    setActionError(null);
    try {
      await createSurvey({ title: CONFERENCE_TITLE, description: null, questions: [CONFERENCE_MARKER] });
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setCreating(false);
    }
  }, [refresh]);

  const runAction = useCallback(async (surveyId: number, action: () => Promise<unknown>) => {
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
  }, [refresh]);

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
      {actionError && <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>}

      <Card>
        <strong>{editingId != null ? "Редактирование опроса" : "Новый опрос"}</strong>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
          <input placeholder="Название" value={title} onChange={(e) => setTitle(e.target.value)} style={inputStyle} />
          <textarea placeholder="Описание (необязательно)" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} style={inputStyle} />
          <textarea placeholder="Вопросы, каждый на новой строке" value={questionsText} onChange={(e) => setQuestionsText(e.target.value)} rows={4} style={inputStyle} />
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <button type="button" className="era-btn-primary" disabled={creating || !title.trim() || textToQuestions(questionsText).length === 0} onClick={() => void handleSave()}>
              {editingId != null ? "Сохранить" : "Создать опрос"}
            </button>
            {editingId != null && <button type="button" onClick={resetForm}>Отмена</button>}
            {editingId == null && <button type="button" disabled={creating} onClick={() => void handleMonthlyTemplate()}>Ежемесячный шаблон</button>}
            {editingId == null && <button type="button" disabled={creating} onClick={() => void handleConferenceTemplate()}>Спикеры конференции</button>}
          </div>
        </div>
      </Card>

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить опросы." />}
      {state.status === "ready" && state.data.length === 0 && <EmptyState text="Опросов пока нет." />}
      {state.status === "ready" && state.data.map((survey) => {
        const conference = isConferenceSurvey(survey);
        return (
          <Card key={survey.id}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
              <strong>{survey.title}</strong>
              <StatusBadge label={STATUS_LABELS[survey.status] ?? survey.status} tone="violet" />
            </div>
            {survey.description && <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>{survey.description}</p>}
            <p style={{ margin: "0 0 0.5rem", fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>
              {survey.is_monthly ? "Ежемесячный · " : ""}Вопросов: {survey.questions.length} · Ответов: {survey.response_count}
              {survey.sent_at ? ` · Отправлен: ${survey.sent_at.slice(0, 10)}` : ""}
            </p>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              {!conference && survey.status !== "archived" && <button type="button" disabled={busyId === survey.id} onClick={() => startEditing(survey)}>Редактировать</button>}
              {!conference && survey.status !== "archived" && (
                <button type="button" className="era-btn-primary" disabled={busyId === survey.id} onClick={() => void runAction(survey.id, () => sendSurvey(survey.id))}>Отправить</button>
              )}
              {conference && survey.status !== "archived" && (
                <button type="button" className="era-btn-primary" disabled={busyId === survey.id} onClick={() => void runAction(survey.id, () => sendChatBroadcast("general", CONFERENCE_CHAT_TEXT))}>
                  Опубликовать в общий чат
                </button>
              )}
              <button type="button" disabled={loadingResponses} onClick={() => void openResponses(survey)}>Результаты ({survey.response_count})</button>
              {survey.status !== "archived" && <button type="button" disabled={busyId === survey.id} onClick={() => void runAction(survey.id, () => archiveSurvey(survey.id))}>Архивировать</button>}
            </div>

            {responsesFor?.id === survey.id && (
              <div style={{ marginTop: "0.75rem", borderTop: "1px solid var(--era-border)", paddingTop: "0.65rem" }}>
                {loadingResponses && <p style={{ color: "var(--era-text-muted)" }}>Загрузка результатов…</p>}
                {!loadingResponses && responses.length === 0 && <p style={{ color: "var(--era-text-muted)", margin: 0 }}>Ответов пока нет.</p>}
                {!loadingResponses && conference && ranking.length > 0 && (
                  <div style={{ marginBottom: "0.8rem" }}>
                    <strong>Рейтинг спикеров</strong>
                    <p style={{ margin: "0.2rem 0 0.5rem", color: "var(--era-text-muted)", fontSize: "0.78rem" }}>Голосов участников: {responses.length}</p>
                    {ranking.map((item, index) => (
                      <div key={item.name} style={{ display: "flex", justifyContent: "space-between", gap: "0.6rem", padding: "0.28rem 0", borderBottom: "1px solid var(--era-border)" }}>
                        <span style={{ fontSize: "0.82rem" }}>{index + 1}. {item.name}</span>
                        <strong style={{ fontSize: "0.82rem", whiteSpace: "nowrap" }}>{item.votes} · {item.percent}%</strong>
                      </div>
                    ))}
                    {customSuggestions.length > 0 && (
                      <div style={{ marginTop: "0.75rem" }}>
                        <strong style={{ fontSize: "0.85rem" }}>Предложили сами</strong>
                        <p style={{ margin: "0.25rem 0 0", fontSize: "0.8rem", color: "var(--era-text-muted)" }}>{customSuggestions.join(" · ")}</p>
                      </div>
                    )}
                  </div>
                )}
                {!loadingResponses && responses.map((response) => (
                  <div key={response.user_id} style={{ marginBottom: "0.5rem" }}>
                    <strong style={{ fontSize: "0.875rem" }}>{response.user_name}</strong>
                    {response.answers.map((answer, index) => (
                      <p key={index} style={{ margin: "0.125rem 0", fontSize: "0.8125rem" }}>
                        <span style={{ color: "var(--era-text-muted)" }}>{answer.question}:</span> {displayAnswer(answer.answer)}
                      </p>
                    ))}
                  </div>
                ))}
                <button type="button" onClick={() => setResponsesFor(null)}>Закрыть</button>
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
