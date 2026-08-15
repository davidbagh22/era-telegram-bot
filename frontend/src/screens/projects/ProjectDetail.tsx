import { useEffect, useMemo, useState } from "react";
import {
  cancelProject,
  describeActionError,
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
  return index >= 0 ? index : Math.max(questions.length - 1, 0);
}

function actionMessage(error: unknown, fallback: string): string {
  const message = describeActionError(error);
  return message.startsWith("Не удалось выполнить действие") ? fallback : message;
}

export function ProjectDetail({ projectId, onBack, initialShowWorkspace = false }: ProjectDetailProps) {
  const [project, setProject] = useState<ProjectDetailType | null>(null);
  const [questions, setQuestions] = useState<ProjectQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [savedNotice, setSavedNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [showWorkspace, setShowWorkspace] = useState(initialShowWorkspace);

  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    Promise.all([fetchProject(projectId), fetchProjectBuilderQuestions()])
      .then(([projectData, questionData]) => {
        if (cancelled) return;
        const formData = projectData.form_data ?? {};
        setProject(projectData);
        setQuestions(questionData);
        setAnswers(formData);
        const nextIndex = firstUnansweredIndex(questionData, formData);
        setQuestionIndex(nextIndex);
        const answeredCount = questionData.filter((question) => (formData[question.key] ?? "").trim()).length;
        if (projectData.can_edit && answeredCount <= 1) setEditing(true);
      })
      .catch(() => {
        if (!cancelled) setLoadError("Не удалось загрузить проект. Попробуйте открыть его ещё раз.");
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const answeredQuestions = useMemo(
    () => questions.filter((question) => (answers[question.key] ?? "").trim()),
    [answers, questions],
  );

  if (loadError) return <EmptyState text={loadError} />;
  if (!project) return <p style={{ color: "var(--era-text-muted)" }}>Загрузка проекта…</p>;

  const currentQuestion = questions[questionIndex] ?? null;
  const progress = questions.length ? Math.round((answeredQuestions.length / questions.length) * 100) : 0;

  const saveQuestion = async (question: ProjectQuestion) => {
    // Send only the field being edited. Older projects can contain technical
    // values in form_data (team-search state, dates, etc.); sending the whole
    // JSON blob back as dict<string,string> made one unrelated legacy value
    // capable of breaking every save step. A project step is now an actual
    // partial PATCH and cannot be poisoned by unrelated project metadata.
    const value = answers[question.key] ?? "";
    const updated = await updateProject(projectId, { [question.key]: value });
    setProject(updated);
    const savedValue = updated.form_data?.[question.key];
    if (typeof savedValue === "string") {
      setAnswers((previous) => ({ ...previous, [question.key]: savedValue }));
    }
    return updated;
  };

  const handleNext = async () => {
    if (!currentQuestion) return;
    if (!(answers[currentQuestion.key] ?? "").trim()) {
      setActionError("Заполните этот шаг — так проект не останется пустой карточкой.");
      return;
    }
    setBusy(true);
    setActionError(null);
    setSavedNotice(null);
    try {
      await saveQuestion(currentQuestion);
      setSavedNotice("Сохранено");
      if (questionIndex < questions.length - 1) {
        setQuestionIndex((index) => index + 1);
      } else {
        setEditing(false);
      }
    } catch (error) {
      setActionError(actionMessage(error, "Не удалось сохранить этот шаг. Ответ остался на экране — попробуйте ещё раз."));
    } finally {
      setBusy(false);
    }
  };

  const handleSaveAndClose = async () => {
    if (!currentQuestion) {
      setEditing(false);
      return;
    }
    const value = answers[currentQuestion.key] ?? "";
    if (!value.trim()) {
      setEditing(false);
      return;
    }
    setBusy(true);
    setActionError(null);
    try {
      await saveQuestion(currentQuestion);
      setEditing(false);
      setSavedNotice("Черновик сохранён");
    } catch (error) {
      setActionError(actionMessage(error, "Не удалось сохранить текущий ответ. Он не потерян — повторите сохранение."));
    } finally {
      setBusy(false);
    }
  };

  const handleSubmit = async () => {
    setBusy(true);
    setActionError(null);
    setSavedNotice(null);
    try {
      const updated = await submitProject(projectId);
      setProject(updated);
      setAnswers(updated.form_data ?? answers);
      setSavedNotice("Проект отправлен на рассмотрение команды ЭРА");
    } catch (error) {
      setActionError(actionMessage(error, "Не удалось отправить проект на рассмотрение. Проверьте соединение и попробуйте снова."));
    } finally {
      setBusy(false);
    }
  };

  const handleCancel = async () => {
    setBusy(true);
    setActionError(null);
    try {
      const updated = await cancelProject(projectId);
      setProject(updated);
      setSavedNotice("Проект удалён из активной работы");
    } catch (error) {
      setActionError(actionMessage(error, "Не удалось удалить проект."));
    } finally {
      setBusy(false);
    }
  };

  const openEditor = () => {
    setActionError(null);
    setSavedNotice(null);
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
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "flex-start" }}>
          <div style={{ minWidth: 0 }}>
            <p style={{ margin: "0 0 0.25rem", color: "rgba(255,255,255,0.7)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
              Проект ЭРА
            </p>
            <strong style={{ display: "block", fontFamily: "var(--era-font-display)", fontSize: "var(--era-text-xl)", overflowWrap: "anywhere" }}>
              {project.title}
            </strong>
            {project.short_description && <p style={{ margin: "0.5rem 0 0", color: "rgba(255,255,255,0.82)" }}>{project.short_description}</p>}
          </div>
          <StatusBadge label={projectStatusLabel(project.status)} tone="violet" />
        </div>
      </Card>

      {actionError && (
        <Card style={{ borderColor: "rgba(255,68,100,0.45)", background: "rgba(255,48,72,0.07)" }}>
          <strong style={{ color: "var(--era-error)" }}>Не сохранилось</strong>
          <p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)", lineHeight: 1.45 }}>{actionError}</p>
        </Card>
      )}
      {savedNotice && !actionError && (
        <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.78rem" }}>✓ {savedNotice}</p>
      )}

      {project.admin_comment && (
        <Card>
          <strong>Комментарий команды ЭРА</strong>
          <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)" }}>{project.admin_comment}</p>
        </Card>
      )}

      {editing && currentQuestion ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", marginBottom: "0.35rem" }}>
              <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
                Конструктор · {questionIndex + 1}/{questions.length}
              </p>
              <strong style={{ fontSize: "var(--era-text-xs)" }}>{progress}%</strong>
            </div>
            <div style={{ height: 6, borderRadius: 999, background: "var(--era-ring-track)", overflow: "hidden" }}>
              <div style={{ width: `${progress}%`, height: "100%", borderRadius: 999, background: "var(--era-gradient)", transition: "width var(--era-motion)" }} />
            </div>
          </div>

          <Card style={{ borderColor: "rgba(255,48,72,0.28)" }}>
            <p style={{ margin: "0 0 0.25rem", color: "var(--era-red)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
              {currentQuestion.block}
            </p>
            <h2 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>{currentQuestion.title}</h2>
            <p style={{ margin: "0.6rem 0 0", color: "var(--era-text-muted)", lineHeight: 1.55, whiteSpace: "pre-wrap" }}>
              {currentQuestion.prompt}
            </p>
          </Card>

          {currentQuestion.ai_hint && (
            <Card style={{ background: "linear-gradient(135deg, rgba(255,48,72,0.10), rgba(107,60,255,0.12)), var(--era-surface)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
                <strong>✨ Подсказка для ИИ</strong>
                <button type="button" onClick={() => void copyAiPrompt(currentQuestion)} style={{ minHeight: "2.25rem", padding: "0.4rem 0.7rem" }}>
                  {copiedKey === currentQuestion.key ? "Скопировано" : "Копировать"}
                </button>
              </div>
              <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)", lineHeight: 1.45, whiteSpace: "pre-wrap" }}>
                {currentQuestion.ai_hint}
              </p>
            </Card>
          )}

          <Card>
            <label htmlFor={`project-answer-${currentQuestion.key}`} style={{ display: "block", fontWeight: 800, marginBottom: "0.5rem" }}>
              Ваш ответ
            </label>
            <textarea
              id={`project-answer-${currentQuestion.key}`}
              value={answers[currentQuestion.key] ?? ""}
              onChange={(event) => {
                setAnswers((previous) => ({ ...previous, [currentQuestion.key]: event.target.value }));
                setActionError(null);
                setSavedNotice(null);
              }}
              rows={6}
              placeholder="Пишите своими словами — дальше это станет структурой проекта"
              style={{ minHeight: 150 }}
            />
          </Card>

          <div style={{ display: "grid", gridTemplateColumns: questionIndex > 0 ? "0.8fr 1.2fr" : "1fr", gap: "0.5rem" }}>
            {questionIndex > 0 && (
              <button type="button" disabled={busy} onClick={() => { setActionError(null); setQuestionIndex((index) => Math.max(0, index - 1)); }}>← Назад</button>
            )}
            <button type="button" className="era-btn-primary" disabled={busy} onClick={() => void handleNext()}>
              {busy ? "Сохраняю…" : questionIndex === questions.length - 1 ? "Сохранить проект" : "Сохранить и дальше →"}
            </button>
          </div>
          <button type="button" disabled={busy} onClick={() => void handleSaveAndClose()}>
            Сохранить и выйти
          </button>
        </div>
      ) : (
        <>
          <Card>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem" }}>
              <div>
                <strong style={{ fontSize: "var(--era-text-lg)" }}>Паспорт проекта</strong>
                <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
                  Заполнено {answeredQuestions.length} из {questions.length} блоков
                </p>
              </div>
              {project.can_edit && <button type="button" onClick={openEditor}>{answeredQuestions.length ? "Редактировать" : "Начать"}</button>}
            </div>
            {answeredQuestions.length === 0 ? (
              <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)" }}>Пока есть только идея. Откройте конструктор и доведите её до полноценного проекта.</p>
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
            <button type="button" className="era-btn-primary" disabled={busy || answeredQuestions.length === 0} onClick={() => void handleSubmit()}>
              {busy ? "Отправляем…" : "Отправить на рассмотрение"}
            </button>
          )}
          {project.can_delete && <button type="button" disabled={busy} onClick={() => void handleCancel()}>Удалить проект</button>}

          <button type="button" onClick={() => setShowWorkspace((value) => !value)}>
            {showWorkspace ? "Скрыть рабочую зону" : "Открыть рабочую зону →"}
          </button>
          {showWorkspace && <ProjectWorkspace projectId={projectId} />}
        </>
      )}
    </div>
  );
}
