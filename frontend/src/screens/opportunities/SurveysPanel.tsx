import { useCallback, useState } from "react";
import { describeActionError, fetchSurvey, fetchSurveys, submitSurvey } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { useAsync } from "../../hooks/useAsync";
import type { SurveyQuestionSpec } from "../../types/opportunity";

function selectedValues(raw: string): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function fallbackSpec(text: string): SurveyQuestionSpec {
  return { text, type: "text", options: [], required: true, max_selections: null, searchable: false };
}

export function SurveysPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchSurveys(), [refreshKey]);
  const [openId, setOpenId] = useState<number | null>(null);
  const [drafts, setDrafts] = useState<Record<number, string[]>>({});
  const [searches, setSearches] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const toggleOpen = useCallback(async (surveyId: number, questionCount: number, completed: boolean) => {
    if (openId === surveyId) {
      setOpenId(null);
      return;
    }
    setOpenId(surveyId);
    setActionError(null);
    if (drafts[surveyId]) return;
    if (completed) {
      try {
        const detail = await fetchSurvey(surveyId);
        setDrafts((previous) => ({ ...previous, [surveyId]: detail.answers ?? Array(questionCount).fill("") }));
        return;
      } catch {
        // The form can still be opened with empty answers if loading the previous response fails.
      }
    }
    setDrafts((previous) => ({ ...previous, [surveyId]: Array(questionCount).fill("") }));
  }, [drafts, openId]);

  const handleAnswerChange = useCallback((surveyId: number, index: number, value: string) => {
    setDrafts((previous) => {
      const answers = [...(previous[surveyId] ?? [])];
      answers[index] = value;
      return { ...previous, [surveyId]: answers };
    });
  }, []);

  const handleChoiceToggle = useCallback((surveyId: number, index: number, value: string, maxSelections: number | null) => {
    setDrafts((previous) => {
      const answers = [...(previous[surveyId] ?? [])];
      const selected = selectedValues(answers[index] ?? "");
      const exists = selected.includes(value);
      if (!exists && maxSelections != null && selected.length >= maxSelections) {
        setActionError(`Можно выбрать не больше ${maxSelections} спикеров`);
        return previous;
      }
      const next = exists ? selected.filter((item) => item !== value) : [...selected, value];
      answers[index] = JSON.stringify(next);
      setActionError(null);
      return { ...previous, [surveyId]: answers };
    });
  }, []);

  const handleSubmit = useCallback(async (surveyId: number, specs: SurveyQuestionSpec[]) => {
    const answers = drafts[surveyId] ?? [];
    const invalid = specs.some((spec, index) => {
      const answer = answers[index] ?? "";
      if (!spec.required) return false;
      if (spec.type === "multiple_choice") return selectedValues(answer).length === 0;
      return !answer.trim();
    });
    if (invalid) {
      setActionError("Сделай выбор перед отправкой");
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
  }, [drafts, refresh]);

  if (state.status === "loading") return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  if (state.status === "error") return <EmptyState text="Не удалось загрузить опросы." />;
  if (state.data.length === 0) return <EmptyState text="Активных опросов пока нет." />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {actionError && <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>}
      {state.data.map((survey) => {
        const isOpen = openId === survey.id;
        const answers = drafts[survey.id] ?? Array(survey.questions.length).fill("");
        const specs = survey.questions.map((question, index) => survey.question_specs[index] ?? fallbackSpec(question));
        return (
          <Card key={survey.id}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
              <strong>{survey.title}</strong>
              <StatusBadge label={survey.completed ? "пройден" : "новый"} tone={survey.completed ? "neutral" : "violet"} />
            </div>
            {survey.description && <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>{survey.description}</p>}
            {!isOpen && (
              <button type="button" className="era-btn-primary" onClick={() => void toggleOpen(survey.id, survey.questions.length, survey.completed)}>
                {survey.completed ? "Изменить выбор" : "Выбрать"}
              </button>
            )}
            {isOpen && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
                {specs.map((spec, index) => {
                  if (spec.type === "multiple_choice") {
                    const selected = selectedValues(answers[index] ?? "");
                    const searchKey = `${survey.id}:${index}`;
                    const query = (searches[searchKey] ?? "").trim().toLowerCase();
                    const visibleOptions = spec.options.filter((option) => !query || `${option.label} ${option.description}`.toLowerCase().includes(query));
                    return (
                      <div key={index} style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
                        <div>
                          <strong style={{ fontSize: "0.9rem" }}>{spec.text}</strong>
                          <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "0.78rem" }}>
                            Выбрано: {selected.length}{spec.max_selections != null ? ` из ${spec.max_selections}` : ""}
                          </p>
                        </div>
                        {spec.searchable && (
                          <input type="search" placeholder="Найти спикера" value={searches[searchKey] ?? ""} onChange={(event) => setSearches((previous) => ({ ...previous, [searchKey]: event.target.value }))} style={{ width: "100%" }} />
                        )}
                        <div style={{ display: "flex", flexDirection: "column", gap: "0.45rem", maxHeight: "58vh", overflowY: "auto" }}>
                          {visibleOptions.map((option) => {
                            const checked = selected.includes(option.value);
                            return (
                              <label key={option.value} style={{ display: "flex", alignItems: "flex-start", gap: "0.65rem", padding: "0.7rem", border: checked ? "1px solid var(--era-violet)" : "1px solid var(--era-border)", borderRadius: "var(--era-radius-control)", background: checked ? "var(--era-tint-violet)" : "var(--era-surface)" }}>
                                <input type="checkbox" checked={checked} onChange={() => handleChoiceToggle(survey.id, index, option.value, spec.max_selections)} style={{ marginTop: "0.2rem" }} />
                                <span>
                                  <strong style={{ display: "block", fontSize: "0.86rem" }}>{option.label}</strong>
                                  {option.description && <span style={{ color: "var(--era-text-muted)", fontSize: "0.76rem", lineHeight: 1.4 }}>{option.description}</span>}
                                </span>
                              </label>
                            );
                          })}
                        </div>
                      </div>
                    );
                  }
                  return (
                    <label key={index} style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                      <span style={{ fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>{spec.text}{spec.required ? "" : " · необязательно"}</span>
                      <textarea rows={2} value={answers[index] ?? ""} onChange={(event) => handleAnswerChange(survey.id, index, event.target.value)} />
                    </label>
                  );
                })}
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button type="button" className="era-btn-primary" disabled={busyId === survey.id} onClick={() => void handleSubmit(survey.id, specs)}>Сохранить выбор</button>
                  <button type="button" onClick={() => setOpenId(null)}>Отмена</button>
                </div>
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
