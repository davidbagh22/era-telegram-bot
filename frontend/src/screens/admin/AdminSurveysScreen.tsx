import { useCallback, useMemo, useState, type CSSProperties } from "react";
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
import { useAsync } from "../../hooks/useAsync";
import type { SurveyAdmin, SurveyResponseAdmin } from "../../types/admin";
import { downloadSurveyResultsExcel } from "./SurveyResultsDownload";

const inputStyle: CSSProperties = {
  width: "100%",
  fontFamily: "var(--era-font-body)",
  padding: "0.75rem 0.8rem",
  borderRadius: "0.75rem",
  border: "1px solid var(--era-border)",
  background: "var(--era-surface)",
  color: "var(--era-text)",
  fontSize: "0.9rem",
  boxSizing: "border-box",
};

const secondaryButtonStyle: CSSProperties = {
  minHeight: 44,
  border: "1px solid var(--era-border)",
  borderRadius: "0.8rem",
  background: "var(--era-surface)",
  color: "var(--era-text)",
  fontWeight: 700,
  padding: "0.7rem 0.9rem",
};

const quietButtonStyle: CSSProperties = {
  minHeight: 40,
  border: "0",
  borderRadius: "0.75rem",
  background: "var(--era-bg)",
  color: "var(--era-text-muted)",
  fontWeight: 650,
  padding: "0.6rem 0.8rem",
};

const STATUS_LABELS: Record<string, string> = {
  draft: "Черновик",
  active: "Активен",
  sent: "Отправлен",
  archived: "Архив",
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

function displaySubmittedAt(value: string | null): string {
  if (!value) return "Без даты";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
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

function StatusPill({ status }: { status: string }) {
  const active = status === "active" || status === "sent";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.35rem",
        flexShrink: 0,
        borderRadius: 999,
        padding: "0.36rem 0.62rem",
        border: active ? "1px solid rgba(111,45,189,0.22)" : "1px solid var(--era-border)",
        background: active ? "var(--era-tint-violet)" : "var(--era-bg)",
        color: active ? "var(--era-violet)" : "var(--era-text-muted)",
        fontSize: "0.72rem",
        lineHeight: 1,
        fontWeight: 800,
        whiteSpace: "nowrap",
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 6,
          height: 6,
          borderRadius: 999,
          background: active ? "var(--era-violet)" : "var(--era-text-muted)",
        }}
      />
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

function MetricChip({ value, label }: { value: string | number; label: string }) {
  return (
    <div
      style={{
        minWidth: 0,
        padding: "0.58rem 0.68rem",
        borderRadius: "0.8rem",
        background: "var(--era-bg)",
        border: "1px solid var(--era-border)",
      }}
    >
      <strong style={{ display: "block", fontSize: "0.92rem", lineHeight: 1.1 }}>{value}</strong>
      <span style={{ display: "block", marginTop: "0.18rem", color: "var(--era-text-muted)", fontSize: "0.69rem" }}>{label}</span>
    </div>
  );
}

function answerLabel(index: number, question: string, conference: boolean): string {
  if (!conference) return question;
  if (index === 0) return "Выбрал";
  if (index === 1) return "Свой кандидат";
  return question;
}

export function AdminSurveysScreen() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAdminSurveys(), [refreshKey]);
  const [showComposer, setShowComposer] = useState(false);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [questionsText, setQuestionsText] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [responsesFor, setResponsesFor] = useState<SurveyAdmin | null>(null);
  const [responses, setResponses] = useState<SurveyResponseAdmin[]>([]);
  const [loadingResponses, setLoadingResponses] = useState(false);
  const [showAllRanking, setShowAllRanking] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);
  const ranking = useMemo(
    () => responsesFor && isConferenceSurvey(responsesFor) ? buildRanking(responses) : [],
    [responsesFor, responses],
  );
  const customSuggestions = useMemo(() => {
    if (!responsesFor || !isConferenceSurvey(responsesFor)) return [];
    return [...new Set(
      responses
        .map((response) => response.answers[1]?.answer?.trim())
        .filter((answer): answer is string => Boolean(answer)),
    )];
  }, [responsesFor, responses]);

  const resetForm = useCallback(() => {
    setTitle("");
    setDescription("");
    setQuestionsText("");
    setEditingId(null);
    setShowComposer(false);
  }, []);

  const startEditing = useCallback((survey: SurveyAdmin) => {
    setEditingId(survey.id);
    setTitle(survey.title);
    setDescription(survey.description ?? "");
    setQuestionsText(questionsToText(survey.questions));
    setShowComposer(true);
    setActionError(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
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
      setShowComposer(false);
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
      setShowComposer(false);
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
    if (responsesFor?.id === survey.id) {
      setResponsesFor(null);
      return;
    }
    setResponsesFor(survey);
    setResponses([]);
    setShowAllRanking(false);
    setLoadingResponses(true);
    setActionError(null);
    try {
      setResponses(await fetchSurveyResponses(survey.id));
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setLoadingResponses(false);
    }
  }, [responsesFor]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem", paddingBottom: "0.5rem" }}>
      {actionError && (
        <div style={{ padding: "0.72rem 0.8rem", borderRadius: "0.8rem", background: "var(--era-bg)", color: "var(--era-error)", fontSize: "0.8rem" }}>
          {actionError}
        </div>
      )}

      <Card gradient style={{ padding: "1rem 1.05rem" }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "0.9rem" }}>
          <div>
            <span style={{ display: "block", color: "var(--era-violet)", fontWeight: 800, fontSize: "0.72rem", letterSpacing: "0.05em", textTransform: "uppercase" }}>Связь с участниками</span>
            <h2 style={{ margin: "0.2rem 0 0", fontSize: "1.35rem", lineHeight: 1.15 }}>Опросы</h2>
            <p style={{ margin: "0.38rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8rem", lineHeight: 1.45 }}>
              Создание, публикация и результаты — в одном месте.
            </p>
          </div>
          <button
            type="button"
            className="era-btn-primary"
            style={{ minWidth: 44, minHeight: 44, padding: "0 0.85rem", flexShrink: 0 }}
            onClick={() => {
              if (showComposer && editingId == null) setShowComposer(false);
              else {
                setEditingId(null);
                setTitle("");
                setDescription("");
                setQuestionsText("");
                setShowComposer(true);
              }
            }}
          >
            {showComposer && editingId == null ? "Закрыть" : "+ Новый"}
          </button>
        </div>
      </Card>

      {showComposer && (
        <Card style={{ padding: "1rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.6rem" }}>
            <div>
              <strong style={{ fontSize: "1rem" }}>{editingId != null ? "Редактирование" : "Новый опрос"}</strong>
              <p style={{ margin: "0.18rem 0 0", color: "var(--era-text-muted)", fontSize: "0.73rem" }}>
                Один вопрос — одна строка.
              </p>
            </div>
            <button type="button" style={quietButtonStyle} onClick={resetForm}>Отмена</button>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.62rem", marginTop: "0.8rem" }}>
            <input placeholder="Название опроса" value={title} onChange={(event) => setTitle(event.target.value)} style={inputStyle} />
            <textarea placeholder="Короткое описание (необязательно)" value={description} onChange={(event) => setDescription(event.target.value)} rows={2} style={inputStyle} />
            <textarea placeholder="Вопросы" value={questionsText} onChange={(event) => setQuestionsText(event.target.value)} rows={4} style={inputStyle} />
            <button
              type="button"
              className="era-btn-primary"
              style={{ width: "100%", minHeight: 46 }}
              disabled={creating || !title.trim() || textToQuestions(questionsText).length === 0}
              onClick={() => void handleSave()}
            >
              {editingId != null ? "Сохранить изменения" : "Создать опрос"}
            </button>
            {editingId == null && (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
                <button type="button" style={secondaryButtonStyle} disabled={creating} onClick={() => void handleMonthlyTemplate()}>Ежемесячный</button>
                <button type="button" style={secondaryButtonStyle} disabled={creating} onClick={() => void handleConferenceTemplate()}>Спикеры</button>
              </div>
            )}
          </div>
        </Card>
      )}

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить опросы." />}
      {state.status === "ready" && state.data.length === 0 && <EmptyState text="Опросов пока нет." />}

      {state.status === "ready" && state.data.map((survey) => {
        const conference = isConferenceSurvey(survey);
        const resultsOpen = responsesFor?.id === survey.id;
        const visibleRanking = showAllRanking ? ranking : ranking.slice(0, 10);
        const maxVotes = Math.max(1, ranking[0]?.votes ?? 1);

        return (
          <Card key={survey.id} style={{ padding: "1rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.75rem" }}>
              <div style={{ minWidth: 0 }}>
                <h3 style={{ margin: 0, fontSize: "1.03rem", lineHeight: 1.3 }}>{survey.title}</h3>
                {survey.description && (
                  <p style={{ margin: "0.38rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8rem", lineHeight: 1.48 }}>
                    {survey.description}
                  </p>
                )}
              </div>
              <StatusPill status={survey.status} />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.48rem", marginTop: "0.8rem" }}>
              <MetricChip value={survey.response_count} label="ответов" />
              <MetricChip value={survey.questions.length} label="вопроса" />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", marginTop: "0.72rem" }}>
              {conference && survey.status !== "archived" && (
                <button
                  type="button"
                  className="era-btn-primary"
                  style={{ gridColumn: "1 / -1", width: "100%", minHeight: 46 }}
                  disabled={busyId === survey.id}
                  onClick={() => void runAction(survey.id, () => sendChatBroadcast("general", CONFERENCE_CHAT_TEXT))}
                >
                  Опубликовать в общий чат
                </button>
              )}
              {!conference && survey.status !== "archived" && (
                <button type="button" className="era-btn-primary" style={{ minHeight: 44 }} disabled={busyId === survey.id} onClick={() => void runAction(survey.id, () => sendSurvey(survey.id))}>Отправить</button>
              )}
              {!conference && survey.status !== "archived" && (
                <button type="button" style={secondaryButtonStyle} disabled={busyId === survey.id} onClick={() => startEditing(survey)}>Изменить</button>
              )}
              <button
                type="button"
                style={{ ...secondaryButtonStyle, gridColumn: conference ? undefined : "1 / -1", borderColor: resultsOpen ? "rgba(111,45,189,0.34)" : "var(--era-border)", background: resultsOpen ? "var(--era-tint-violet)" : "var(--era-surface)" }}
                disabled={loadingResponses && !resultsOpen}
                onClick={() => void openResponses(survey)}
              >
                {resultsOpen ? "Скрыть результаты" : `Результаты · ${survey.response_count}`}
              </button>
              {survey.status !== "archived" && (
                <button type="button" style={quietButtonStyle} disabled={busyId === survey.id} onClick={() => void runAction(survey.id, () => archiveSurvey(survey.id))}>В архив</button>
              )}
            </div>

            {resultsOpen && (
              <div style={{ marginTop: "1rem", paddingTop: "1rem", borderTop: "1px solid var(--era-border)" }}>
                {loadingResponses && <p style={{ color: "var(--era-text-muted)", margin: 0 }}>Загружаю результаты…</p>}
                {!loadingResponses && responses.length === 0 && <p style={{ color: "var(--era-text-muted)", margin: 0 }}>Ответов пока нет.</p>}

                {!loadingResponses && responses.length > 0 && (
                  <>
                    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "0.8rem" }}>
                      <div>
                        <span style={{ color: "var(--era-violet)", fontSize: "0.7rem", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.05em" }}>Аналитика</span>
                        <h4 style={{ margin: "0.15rem 0 0", fontSize: "1.08rem" }}>Результаты</h4>
                      </div>
                      <span style={{ color: "var(--era-text-muted)", fontSize: "0.72rem", paddingTop: "0.2rem" }}>{responses.length} ответов</span>
                    </div>

                    <button
                      type="button"
                      className="era-btn-primary"
                      style={{ width: "100%", minHeight: 46, marginTop: "0.75rem" }}
                      onClick={() => downloadSurveyResultsExcel(survey, responses, ranking, conference)}
                    >
                      ↓ Скачать Excel-отчёт
                    </button>

                    {conference && ranking.length > 0 && (
                      <section style={{ marginTop: "1rem" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.6rem" }}>
                          <strong style={{ fontSize: "0.95rem" }}>Рейтинг спикеров</strong>
                          <span style={{ color: "var(--era-text-muted)", fontSize: "0.7rem" }}>{ranking.length} в рейтинге</span>
                        </div>

                        <div style={{ display: "flex", flexDirection: "column", gap: "0.48rem", marginTop: "0.62rem" }}>
                          {visibleRanking.map((item, index) => (
                            <div key={item.name} style={{ padding: "0.62rem 0.68rem", border: "1px solid var(--era-border)", borderRadius: "0.8rem", background: index < 3 ? "var(--era-tint-violet)" : "var(--era-surface)" }}>
                              <div style={{ display: "grid", gridTemplateColumns: "1.65rem minmax(0, 1fr) auto", alignItems: "center", gap: "0.48rem" }}>
                                <span style={{ display: "grid", placeItems: "center", width: 26, height: 26, borderRadius: 999, background: index < 3 ? "var(--era-violet)" : "var(--era-bg)", color: index < 3 ? "#fff" : "var(--era-text-muted)", fontSize: "0.7rem", fontWeight: 850 }}>{index + 1}</span>
                                <strong style={{ minWidth: 0, fontSize: "0.8rem", lineHeight: 1.3 }}>{item.name}</strong>
                                <span style={{ whiteSpace: "nowrap", fontSize: "0.74rem", fontWeight: 800 }}>{item.votes} · {item.percent}%</span>
                              </div>
                              <div style={{ height: 4, borderRadius: 999, background: "var(--era-bg)", overflow: "hidden", margin: "0.52rem 0 0 2.12rem" }}>
                                <div style={{ width: `${Math.max(4, Math.round((item.votes / maxVotes) * 100))}%`, height: "100%", borderRadius: 999, background: "var(--era-violet)" }} />
                              </div>
                            </div>
                          ))}
                        </div>

                        {ranking.length > 10 && (
                          <button type="button" style={{ ...quietButtonStyle, width: "100%", marginTop: "0.45rem" }} onClick={() => setShowAllRanking((value) => !value)}>
                            {showAllRanking ? "Свернуть рейтинг" : `Показать все · ${ranking.length}`}
                          </button>
                        )}

                        {customSuggestions.length > 0 && (
                          <div style={{ marginTop: "0.85rem" }}>
                            <strong style={{ fontSize: "0.84rem" }}>Предложили сами</strong>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.38rem", marginTop: "0.45rem" }}>
                              {customSuggestions.map((suggestion) => (
                                <span key={suggestion} style={{ padding: "0.38rem 0.55rem", borderRadius: 999, background: "var(--era-bg)", border: "1px solid var(--era-border)", fontSize: "0.72rem" }}>{suggestion}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </section>
                    )}

                    <section style={{ marginTop: "1.05rem" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.6rem" }}>
                        <strong style={{ fontSize: "0.95rem" }}>Кто за что голосовал</strong>
                        <span style={{ color: "var(--era-text-muted)", fontSize: "0.7rem" }}>Нажми на имя</span>
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.46rem", marginTop: "0.58rem" }}>
                        {responses.map((response) => (
                          <details key={response.user_id} style={{ border: "1px solid var(--era-border)", borderRadius: "0.82rem", background: "var(--era-surface)", overflow: "hidden" }}>
                            <summary style={{ cursor: "pointer", listStyle: "none", padding: "0.68rem 0.72rem", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.7rem" }}>
                              <span style={{ minWidth: 0 }}>
                                <strong style={{ display: "block", fontSize: "0.82rem", lineHeight: 1.25 }}>{response.user_name}</strong>
                                <span style={{ display: "block", marginTop: "0.18rem", color: "var(--era-text-muted)", fontSize: "0.68rem" }}>{displaySubmittedAt(response.submitted_at)}</span>
                              </span>
                              <span aria-hidden="true" style={{ flexShrink: 0, width: 28, height: 28, display: "grid", placeItems: "center", borderRadius: 999, background: "var(--era-bg)", color: "var(--era-violet)", fontWeight: 850 }}>›</span>
                            </summary>
                            <div style={{ padding: "0 0.72rem 0.72rem", borderTop: "1px solid var(--era-border)" }}>
                              {response.answers.map((answer, index) => (
                                <div key={index} style={{ paddingTop: "0.62rem" }}>
                                  <span style={{ display: "block", color: "var(--era-text-muted)", fontSize: "0.68rem", fontWeight: 700 }}>{answerLabel(index, answer.question, conference)}</span>
                                  <p style={{ margin: "0.22rem 0 0", fontSize: "0.8rem", lineHeight: 1.45 }}>{displayAnswer(answer.answer)}</p>
                                </div>
                              ))}
                              <span style={{ display: "block", marginTop: "0.62rem", color: "var(--era-text-muted)", fontSize: "0.62rem" }}>Участник #{response.user_id}</span>
                            </div>
                          </details>
                        ))}
                      </div>
                    </section>
                  </>
                )}
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
