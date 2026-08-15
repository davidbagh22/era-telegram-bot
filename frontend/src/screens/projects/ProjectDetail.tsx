import { useEffect, useMemo, useState } from "react";
import {
  cancelProject,
  fetchProject,
  submitProject,
  updateProject,
} from "../../api/client";
import { fetchProjectBuilderQuestions } from "../../api/projectBuilder";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import type { ProjectDetail as ProjectDetailType, ProjectQuestion } from "../../types/project";
import { projectStatusLabel } from "./statusLabels";
import { ProjectWorkspace } from "./ProjectWorkspace";

interface ProjectDetailProps {
  projectId: number;
  onBack: () => void;
  initialShowWorkspace?: boolean;
}

function firstUnansweredIndex(questions: ProjectQuestion[], answers: Record<string, string>): number {
  const index = questions.findIndex((question) => !(answers[question.key] ?? "").trim());
  return index >= 0 ? index : 0;
}

function draftStorageKey(projectId: number): string {
  return `era:project-builder:${projectId}`;
}

function readLocalDraft(projectId: number): Record<string, string> {
  try {
    const raw = window.localStorage.getItem(draftStorageKey(projectId));
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed).filter((entry): entry is [string, string] => typeof entry[1] === "string"),
    );
  } catch {
    return {};
  }
}

function writeLocalDraft(projectId: number, answers: Record<string, string>): void {
  try {
    if (Object.keys(answers).length === 0) {
      window.localStorage.removeItem(draftStorageKey(projectId));
      return;
    }
    window.localStorage.setItem(draftStorageKey(projectId), JSON.stringify(answers));
  } catch {
    // Device storage is a resilience layer only; a blocked localStorage must
    // never stop the actual server-backed project constructor.
  }
}

function splitPrompt(prompt: string): { question: string; hint: string } {
  const [question, ...rest] = prompt.split(/\n\n+/);
  return { question: question.trim(), hint: rest.join("\n\n").trim() };
}

export function ProjectDetail({ projectId, onBack, initialShowWorkspace = false }: ProjectDetailProps) {
  const [project, setProject] = useState<ProjectDetailType | null>(null);
  const [questions, setQuestions] = useState<ProjectQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [localDraft, setLocalDraft] = useState<Record<string, string>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [showAiPrompt, setShowAiPrompt] = useState(false);
  const [showWorkspace, setShowWorkspace] = useState(initialShowWorkspace);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchProject(projectId), fetchProjectBuilderQuestions()])
      .then(([projectData, questionData]) => {
        if (cancelled) return;
        const deviceDraft = readLocalDraft(projectId);
        const formData = projectData.form_data ?? {};
        const merged = { ...formData, ...deviceDraft };
        setProject(projectData);
        setQuestions(questionData);
        setAnswers(merged);
        setLocalDraft(deviceDraft);
        setQuestionIndex(firstUnansweredIndex(questionData, merged));
        const answeredCount = questionData.filter((question) => (merged[question.key] ?? "").trim()).length;
        if (projectData.can_edit && answeredCount <= 1) setEditing(true);
      })
      .catch(() => {
        if (!cancelled) setLoadError("Не удалось загрузить проект. Проверьте соединение и попробуйте ещё раз.");
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  useEffect(() => {
    setShowAiPrompt(false);
    setSaveError(null);
  }, [questionIndex]);

  const answeredQuestions = useMemo(
    () => questions.filter((question) => (answers[question.key] ?? "").trim()),
    [answers, questions],
  );

  if (loadError) return <EmptyState text={loadError} />;
  if (!project) return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;

  const currentQuestion = questions[questionIndex] ?? null;
  const currentAnswer = currentQuestion ? answers[currentQuestion.key] ?? "" : "";
  const progress = questions.length ? Math.round(((questionIndex + 1) / questions.length) * 100) : 0;
  const promptParts = currentQuestion ? splitPrompt(currentQuestion.prompt) : null;
  const currentHasDeviceDraft = currentQuestion ? Object.hasOwn(localDraft, currentQuestion.key) : false;

  const persistDeviceAnswer = (key: string, value: string) => {
    setLocalDraft((previous) => {
      const next = { ...previous, [key]: value };
      writeLocalDraft(projectId, next);
      return next;
    });
  };

  const clearDeviceAnswer = (key: string) => {
    setLocalDraft((previous) => {
      const next = { ...previous };
      delete next[key];
      writeLocalDraft(projectId, next);
      return next;
    });
  };

  const saveCurrentAnswer = async () => {
    if (!currentQuestion) return project;
    // PATCH only the current step. The API is explicitly partial, and sending
    // the whole historical form on every tap made one stale/legacy field able
    // to break an otherwise valid new answer.
    const updated = await updateProject(projectId, { [currentQuestion.key]: currentAnswer });
    setProject(updated);
    clearDeviceAnswer(currentQuestion.key);
    return updated;
  };

  const handleNext = async () => {
    if (!currentQuestion || !currentAnswer.trim()) return;
    setBusy(true);
    setSaveError(null);
    try {
      await saveCurrentAnswer();
      if (questionIndex < questions.length - 1) {
        setQuestionIndex((index) => index + 1);
      } else {
        setEditing(false);
      }
    } catch {
      setSaveError("Шаг не сохранился на сервере. Ваш текст остался здесь и сохранён на устройстве — нажмите «Повторить сохранение».");
    } finally {
      setBusy(false);
    }
  };

  const handlePrevious = async () => {
    if (questionIndex <= 0) return;
    if (!currentQuestion || !currentAnswer.trim()) {
      setQuestionIndex((index) => Math.max(0, index - 1));
      return;
    }
    setBusy(true);
    setSaveError(null);
    try {
      await saveCurrentAnswer();
      setQuestionIndex((index) => Math.max(0, index - 1));
    } catch {
      setSaveError("Не удалось синхронизировать этот ответ. Текст сохранён на устройстве; можно повторить или продолжить позже.");
    } finally {
      setBusy(false);
    }
  };

  const handleSubmit = async () => {
    setBusy(true);
    try {
      const updated = await submitProject(projectId);
      setProject(updated);
    } finally {
      setBusy(false);
    }
  };

  const handleCancel = async () => {
    setBusy(true);
    try {
      const updated = await cancelProject(projectId);
      setProject(updated);
      writeLocalDraft(projectId, {});
      setLocalDraft({});
    } finally {
      setBusy(false);
    }
  };

  const openEditor = () => {
    setQuestionIndex(firstUnansweredIndex(questions, answers));
    setEditing(true);
  };

  const copyAiPrompt = async (question: ProjectQuestion) => {
    if (!question.ai_hint) return;
    try {
      await navigator.clipboard.writeText(question.ai_hint);
      setCopiedKey(question.key);
      window.setTimeout(() => setCopiedKey((key) => (key === question.key ? null : key)), 1600);
    } catch {
      setCopiedKey(null);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" onClick={onBack}>← К проектам</button>

      <Card gradient style={{ position: "relative", overflow: "hidden" }}>
        <div aria-hidden="true" style={{ position: "absolute", width: 190, height: 190, borderRadius: "50%", right: -80, top: -110, background: "rgba(255,255,255,0.13)", filter: "blur(4px)" }} />
        <div style={{ position: "relative", display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "flex-start" }}>
          <div style={{ minWidth: 0 }}>
            <p style={{ margin: "0 0 0.25rem", color: "rgba(255,255,255,0.72)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
              Проект ЭРА
            </p>
            <strong style={{ display: "block", fontFamily: "var(--era-font-display)", fontSize: "var(--era-text-xl)", overflowWrap: "anywhere" }}>
              {project.title}
            </strong>
            {project.short_description && <p style={{ margin: "0.5rem 0 0", color: "rgba(255,255,255,0.84)" }}>{project.short_description}</p>}
          </div>
          <StatusBadge label={projectStatusLabel(project.status)} tone="violet" />
        </div>
      </Card>

      {project.admin_comment && (
        <Card>
          <strong>Комментарий команды ЭРА</strong>
          <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)" }}>{project.admin_comment}</p>
        </Card>
      )}

      {editing && currentQuestion ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", alignItems: "baseline" }}>
              <p style={{ margin: "0 0 0.35rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
                Конструктор · шаг {questionIndex + 1} из {questions.length}
              </p>
              <strong style={{ fontSize: "var(--era-text-xs)", color: "var(--era-red)" }}>{progress}%</strong>
            </div>
            <div style={{ height: 6, borderRadius: 999, background: "var(--era-ring-track)", overflow: "hidden" }}>
              <div style={{ width: `${progress}%`, height: "100%", borderRadius: 999, background: "var(--era-gradient)", transition: "width var(--era-motion)" }} />
            </div>
          </div>

          <Card style={{ borderColor: "rgba(255,32,56,0.34)", background: "linear-gradient(180deg, rgba(255,32,56,0.08), rgba(255,255,255,0.02)), var(--era-surface)" }}>
            <p style={{ margin: "0 0 0.3rem", color: "var(--era-red)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
              {currentQuestion.block}
            </p>
            <h2 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>{currentQuestion.title}</h2>
            <p style={{ margin: "0.65rem 0 0", fontSize: "var(--era-text-lg)", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
              {promptParts?.question}
            </p>
            {promptParts?.hint && (
              <div style={{ marginTop: "0.75rem", padding: "0.75rem", borderRadius: "var(--era-radius-sm)", background: "rgba(255,255,255,0.055)", border: "1px solid rgba(255,255,255,0.08)" }}>
                <strong style={{ display: "block", fontSize: "var(--era-text-sm)", marginBottom: "0.25rem" }}>Подсказка — как ответить</strong>
                <span style={{ color: "var(--era-text-muted)", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>{promptParts.hint}</span>
              </div>
            )}
          </Card>

          {currentQuestion.ai_hint && (
            <Card style={{ padding: "0.8rem 0.9rem", background: "linear-gradient(135deg, rgba(255,32,56,0.10), rgba(255,37,111,0.08)), var(--era-surface)" }}>
              <button type="button" onClick={() => setShowAiPrompt((value) => !value)} style={{ width: "100%", minHeight: 0, padding: 0, border: "none", background: "transparent", display: "flex", justifyContent: "space-between", alignItems: "center", textAlign: "left" }}>
                <span><strong>✨ Мини-промпт для ИИ</strong><span style={{ display: "block", marginTop: "0.15rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>Если хотите быстро собрать черновик ответа</span></span>
                <span>{showAiPrompt ? "−" : "+"}</span>
              </button>
              {showAiPrompt && (
                <div style={{ marginTop: "0.65rem" }}>
                  <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)", lineHeight: 1.45, whiteSpace: "pre-wrap" }}>
                    {currentQuestion.ai_hint}
                  </p>
                  <button type="button" onClick={() => void copyAiPrompt(currentQuestion)} style={{ marginTop: "0.55rem", minHeight: "2.25rem" }}>
                    {copiedKey === currentQuestion.key ? "✓ Скопировано" : "Скопировать промпт"}
                  </button>
                </div>
              )}
            </Card>
          )}

          <Card>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", alignItems: "baseline", marginBottom: "0.5rem" }}>
              <label htmlFor={`project-answer-${currentQuestion.key}`} style={{ fontWeight: 800 }}>
                Ответ для проекта
              </label>
              {currentHasDeviceDraft && <span style={{ fontSize: "var(--era-text-xs)", color: "var(--era-success)" }}>сохранён на устройстве</span>}
            </div>
            <p style={{ margin: "0 0 0.55rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)", lineHeight: 1.45 }}>
              Напишите своими словами или вставьте ответ ИИ и отредактируйте под себя.
            </p>
            <textarea
              id={`project-answer-${currentQuestion.key}`}
              value={currentAnswer}
              onChange={(event) => {
                const value = event.target.value;
                setAnswers((previous) => ({ ...previous, [currentQuestion.key]: value }));
                persistDeviceAnswer(currentQuestion.key, value);
                setSaveError(null);
              }}
              rows={6}
              placeholder="Ваш ответ…"
              style={{ minHeight: 150 }}
            />
          </Card>

          {saveError && (
            <Card style={{ borderColor: "rgba(255,107,101,0.42)", background: "rgba(255,107,101,0.07)" }}>
              <strong style={{ color: "var(--era-error)" }}>Ответ не потерян</strong>
              <p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)", lineHeight: 1.45 }}>{saveError}</p>
              <button type="button" className="era-btn-primary" disabled={busy || !currentAnswer.trim()} onClick={() => void handleNext()} style={{ marginTop: "0.65rem", width: "100%" }}>
                Повторить сохранение
              </button>
            </Card>
          )}

          <div style={{ display: "grid", gridTemplateColumns: questionIndex > 0 ? "0.8fr 1.2fr" : "1fr", gap: "0.5rem" }}>
            {questionIndex > 0 && (
              <button type="button" disabled={busy} onClick={() => void handlePrevious()}>← Назад</button>
            )}
            <button type="button" className="era-btn-primary" disabled={busy || !currentAnswer.trim()} onClick={() => void handleNext()}>
              {busy ? "Сохраняю…" : questionIndex === questions.length - 1 ? "Сохранить проект" : "Сохранить и дальше →"}
            </button>
          </div>
          <button type="button" disabled={busy} onClick={() => setEditing(false)}>Сохранить черновик и выйти</button>
        </div>
      ) : (
        <>
          <Card>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem" }}>
              <div>
                <strong style={{ fontSize: "var(--era-text-lg)" }}>Конструктор проекта</strong>
                <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
                  Заполнено {answeredQuestions.length} из {questions.length} шагов
                </p>
              </div>
              {project.can_edit && <button type="button" className="era-btn-primary" onClick={openEditor}>Продолжить →</button>}
            </div>
            {answeredQuestions.length === 0 ? (
              <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)" }}>Ответы пока не заполнены.</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem", marginTop: "0.75rem" }}>
                {answeredQuestions.map((question) => (
                  <div key={question.key}>
                    <p style={{ margin: 0, fontSize: "0.8125rem", fontWeight: 700, color: "var(--era-text-muted)" }}>{question.title}</p>
                    <p style={{ margin: "0.25rem 0 0", whiteSpace: "pre-wrap" }}>{answers[question.key]}</p>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {project.can_submit && (
            <button type="button" className="era-btn-primary" disabled={busy} onClick={handleSubmit}>Отправить на рассмотрение</button>
          )}
          {project.can_delete && <button type="button" disabled={busy} onClick={handleCancel}>Удалить проект</button>}

          <button type="button" onClick={() => setShowWorkspace((value) => !value)}>
            {showWorkspace ? "Скрыть рабочее пространство" : "Рабочее пространство →"}
          </button>
          {showWorkspace && <ProjectWorkspace projectId={projectId} />}
        </>
      )}
    </div>
  );
}
