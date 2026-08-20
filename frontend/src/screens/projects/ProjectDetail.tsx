import { useEffect, useMemo, useState } from "react";
import {
  cancelProject,
  describeActionError,
  fetchProject,
  submitProject,
  updateProject,
} from "../../api/client";
import { fetchProjectBuilderQuestions } from "../../api/projectBuilder";
import { BottomSheet } from "../../components/BottomSheet";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { hintForProjectQuestion } from "../../help/projectBuilderHints";
import type { ProjectDetail as ProjectDetailType, ProjectQuestion } from "../../types/project";
import { projectStatusLabel } from "./statusLabels";
import { ProjectWorkspace } from "./ProjectWorkspace";

interface ProjectDetailProps {
  projectId: number;
  onBack: () => void;
  initialShowWorkspace?: boolean;
}

type SaveIntent = "next" | "close";

type PendingRetry = {
  questionKey: string;
  questionIndex: number;
  answer: string;
  intent: SaveIntent;
};

const LEGACY_LABELS: Record<string, string> = {
  department_direction: "Отдел и направление",
  audience_need: "Потребность аудитории",
  differentiator: "Фишка проекта",
  venue_request: "Площадка",
  proposed_date: "Предложенная дата",
  proposed_time: "Предложенное время",
  budget: "Бюджет / расходы",
  marketing_plan: "План продвижения",
  announcement: "Анонс",
  participant_reminder: "Сообщение участникам",
  follow_up_plan: "План после проекта",
};

function firstUnansweredIndex(questions: ProjectQuestion[], answers: Record<string, string>): number {
  const index = questions.findIndex((question) => !(answers[question.key] ?? "").trim());
  return index >= 0 ? index : 0;
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
  const [saveError, setSaveError] = useState<string | null>(null);
  const [pendingRetry, setPendingRetry] = useState<PendingRetry | null>(null);
  const [savedNotice, setSavedNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [showWorkspace, setShowWorkspace] = useState(initialShowWorkspace);
  const [hintOpen, setHintOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

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
    return () => { cancelled = true; };
  }, [projectId]);

  useEffect(() => {
    if (savedNotice !== "Сохранено" && savedNotice !== "Черновик сохранён") return;
    const timeout = window.setTimeout(() => setSavedNotice(null), 1600);
    return () => window.clearTimeout(timeout);
  }, [savedNotice]);

  useEffect(() => {
    setHintOpen(false);
  }, [questionIndex]);

  const answeredQuestions = useMemo(
    () => questions.filter((question) => (answers[question.key] ?? "").trim()),
    [answers, questions],
  );

  const legacyAnswers = useMemo(() => {
    const questionKeys = new Set(questions.map((question) => question.key));
    return Object.entries(answers).filter(([key, value]) => Boolean(value?.trim()) && !questionKeys.has(key) && Boolean(LEGACY_LABELS[key]));
  }, [answers, questions]);

  if (loadError) return <EmptyState text={loadError} />;
  if (!project) return <p style={{ color: "var(--era-text-muted)" }}>Загрузка проекта…</p>;

  const currentQuestion = questions[questionIndex] ?? null;
  const constructorComplete = questions.length > 0 && answeredQuestions.length === questions.length;
  const progress = questions.length ? Math.round((answeredQuestions.length / questions.length) * (constructorComplete ? 100 : 94)) : 0;
  const currentHint = currentQuestion
    ? hintForProjectQuestion(currentQuestion.key, currentQuestion.title, currentQuestion.prompt)
    : null;
  const isDraftLike = project.status === "draft" || project.status === "needs_revision";

  const saveQuestion = async (question: ProjectQuestion, value: string) => {
    const updated = await updateProject(projectId, { [question.key]: value });
    setProject(updated);
    const savedValue = updated.form_data?.[question.key];
    if (typeof savedValue === "string") setAnswers((previous) => ({ ...previous, [question.key]: savedValue }));
    return updated;
  };

  const persistStep = async (question: ProjectQuestion, sourceIndex: number, answer: string, intent: SaveIntent) => {
    setBusy(true);
    setActionError(null);
    setSaveError(null);
    setSavedNotice(null);
    try {
      await saveQuestion(question, answer);
      setPendingRetry(null);
      if (intent === "next") {
        if (sourceIndex < questions.length - 1) {
          setSavedNotice("Сохранено");
          setQuestionIndex(Math.min(sourceIndex + 1, questions.length - 1));
        } else {
          setEditing(false);
          setSavedNotice("Проект собран. Проверьте финальный preview перед отправкой.");
        }
      } else {
        setEditing(false);
        setSavedNotice("Черновик сохранён");
      }
    } catch (error) {
      setSaveError(actionMessage(error, "Не удалось сохранить этот шаг. Ответ не потерян."));
      setPendingRetry({ questionKey: question.key, questionIndex: sourceIndex, answer, intent });
    } finally {
      setBusy(false);
    }
  };

  const handleNext = async () => {
    if (!currentQuestion) return;
    const answer = answers[currentQuestion.key] ?? "";
    if (!answer.trim()) {
      setActionError("Заполните этот шаг своими словами. Теория помогает разобраться, но ответ остаётся вашим.");
      return;
    }
    await persistStep(currentQuestion, questionIndex, answer, "next");
  };

  const handleSaveAndClose = async () => {
    if (!currentQuestion) { setEditing(false); return; }
    const answer = answers[currentQuestion.key] ?? "";
    if (!answer.trim()) { setEditing(false); return; }
    await persistStep(currentQuestion, questionIndex, answer, "close");
  };

  const handleRetrySave = async () => {
    if (!pendingRetry) return;
    const question = questions.find((item) => item.key === pendingRetry.questionKey);
    if (!question) {
      setPendingRetry(null);
      setSaveError(null);
      setActionError("Не удалось определить шаг для повторного сохранения. Откройте конструктор ещё раз.");
      return;
    }
    await persistStep(question, pendingRetry.questionIndex, pendingRetry.answer, pendingRetry.intent);
  };

  const handleSubmit = async () => {
    if (!constructorComplete) {
      setActionError(`Сначала завершите все ${questions.length} шагов конструктора и проверьте финальный preview.`);
      return;
    }
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

  const handleDelete = async () => {
    setBusy(true);
    setActionError(null);
    try {
      await cancelProject(projectId);
      setDeleteOpen(false);
      onBack();
    } catch (error) {
      setDeleteOpen(false);
      setActionError(actionMessage(error, isDraftLike ? "Не удалось удалить черновик." : "Не удалось убрать проект."));
    } finally {
      setBusy(false);
    }
  };

  const openEditor = () => {
    setActionError(null);
    setSaveError(null);
    setPendingRetry(null);
    setSavedNotice(null);
    setQuestionIndex(firstUnansweredIndex(questions, answers));
    setEditing(true);
  };

  return (
    <div className="era-page" style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" onClick={onBack}>← К проектам</button>

      <Card gradient>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "flex-start" }}>
          <div style={{ minWidth: 0 }}>
            <p style={{ margin: "0 0 0.25rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Проект ЭРА</p>
            <strong style={{ display: "block", fontFamily: "var(--era-font-display)", fontSize: "var(--era-text-xl)", overflowWrap: "anywhere" }}>{project.title}</strong>
            {project.short_description && <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)" }}>{project.short_description}</p>}
          </div>
          <StatusBadge label={projectStatusLabel(project.status)} tone="violet" />
        </div>
      </Card>

      {actionError && <Card style={{ borderColor: "rgba(255,102,117,0.35)", background: "rgba(255,102,117,0.06)" }}><strong style={{ color: "var(--era-error)" }}>Нужно действие</strong><p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)", lineHeight: 1.45 }}>{actionError}</p></Card>}
      {saveError && pendingRetry && currentQuestion?.key === pendingRetry.questionKey && (
        <Card style={{ borderColor: "rgba(255,102,117,0.35)", background: "rgba(255,102,117,0.06)" }}>
          <strong style={{ color: "var(--era-error)" }}>Шаг не сохранён</strong>
          <p style={{ margin: "0.3rem 0 0.7rem", color: "var(--era-text-muted)" }}>{saveError}</p>
          <button type="button" className="era-btn-primary" disabled={busy} onClick={() => void handleRetrySave()}>{busy ? "Повторяем…" : "Повторить сохранение"}</button>
        </Card>
      )}
      {editing && busy && <p className="era-save-indicator">● Сохраняем…</p>}
      {savedNotice && !actionError && !saveError && <p className="era-save-indicator" data-state={savedNotice === "Сохранено" || savedNotice === "Черновик сохранён" ? "saved" : "info"}>✓ {savedNotice}</p>}
      {project.admin_comment && <Card><strong>Комментарий команды ЭРА</strong><p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)" }}>{project.admin_comment}</p></Card>}

      {editing && currentQuestion ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", marginBottom: "0.35rem" }}>
              <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Конструктор · {String(questionIndex + 1).padStart(2, "0")} / {String(questions.length).padStart(2, "0")}</p>
              <strong style={{ fontSize: "var(--era-text-xs)" }}>{progress}%</strong>
            </div>
            <div style={{ height: 6, borderRadius: 999, background: "var(--era-ring-track)", overflow: "hidden" }}><div style={{ width: `${progress}%`, height: "100%", borderRadius: 999, background: "var(--era-gradient)", transition: "width 240ms cubic-bezier(0.22,1,0.36,1)" }} /></div>
          </div>

          <div key={currentQuestion.key} className="era-question-step" style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <Card style={{ borderColor: "rgba(99,44,255,0.22)" }}>
              <p style={{ margin: "0 0 0.25rem", color: "var(--era-red-bright)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>{currentQuestion.block}</p>
              <h2 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>{currentQuestion.title}</h2>
              <p style={{ margin: "0.6rem 0 0", color: "var(--era-text-muted)", lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{currentQuestion.prompt}</p>
            </Card>

            {currentHint && (
              <Card style={{ background: "linear-gradient(135deg, rgba(99,44,255,.08), rgba(255,100,0,.05)), var(--era-surface)", borderColor: "rgba(99,44,255,.16)" }}>
                <p style={{ margin: "0 0 0.45rem", color: "var(--era-violet)", fontSize: "var(--era-text-xs)", fontWeight: 850, textTransform: "uppercase" }}>Теория шага</p>
                <strong style={{ display: "block", lineHeight: 1.45 }}>{currentHint.what}</strong>
                <p style={{ margin: "0.55rem 0 0", color: "var(--era-text-muted)", lineHeight: 1.55 }}>{currentHint.why}</p>
                <div style={{ marginTop: "0.75rem", paddingTop: "0.7rem", borderTop: "1px solid var(--era-border)" }}>
                  <strong style={{ display: "block", fontSize: "var(--era-text-sm)" }}>Что написать</strong>
                  <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", lineHeight: 1.5 }}>{currentHint.write}</p>
                </div>
              </Card>
            )}

            <button type="button" onClick={() => setHintOpen(true)} style={{ width: "100%", textAlign: "left", padding: "0.8rem 0.9rem", borderRadius: "var(--era-radius-control)", border: "1px solid rgba(99,44,255,.22)", background: "var(--era-tint-violet)", color: "var(--era-violet)", fontWeight: 800 }}>
              Подробнее: вопросы и ошибки →
            </button>

            <Card>
              <label htmlFor={`project-answer-${currentQuestion.key}`} style={{ display: "block", fontWeight: 800, marginBottom: "0.5rem" }}>Ваш ответ</label>
              <textarea
                id={`project-answer-${currentQuestion.key}`}
                value={answers[currentQuestion.key] ?? ""}
                onChange={(event) => {
                  const value = event.target.value;
                  setAnswers((previous) => ({ ...previous, [currentQuestion.key]: value }));
                  setPendingRetry((previous) => previous?.questionKey === currentQuestion.key ? { ...previous, answer: value } : previous);
                  setActionError(null);
                  setSavedNotice(null);
                }}
                rows={6}
                placeholder="Напишите своими словами. Используйте теорию выше как ориентир."
                style={{ minHeight: 150 }}
              />
            </Card>

            <div style={{ display: "grid", gridTemplateColumns: questionIndex > 0 ? "0.8fr 1.2fr" : "1fr", gap: "0.5rem" }}>
              {questionIndex > 0 && (
                <button type="button" disabled={busy} onClick={() => {
                  if (pendingRetry) { setActionError("Сначала повторите сохранение этого шага — ответ на экране и не потерян."); return; }
                  setActionError(null);
                  setQuestionIndex((index) => Math.max(0, index - 1));
                }}>← Назад</button>
              )}
              <button type="button" className="era-btn-primary" disabled={busy} onClick={() => void handleNext()}>{busy ? "● Сохраняем…" : questionIndex === questions.length - 1 ? "К финальному preview →" : "Сохранить и дальше →"}</button>
            </div>
            <button type="button" disabled={busy} onClick={() => void handleSaveAndClose()}>Сохранить и выйти</button>
            {project.can_delete && isDraftLike && (
              <button type="button" disabled={busy} onClick={() => setDeleteOpen(true)} style={{ color: "var(--era-error)" }}>
                Удалить черновик
              </button>
            )}
          </div>

          {currentHint && (
            <BottomSheet open={hintOpen} onClose={() => setHintOpen(false)} title={`Разбор шага · ${currentHint.title}`}>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem", maxHeight: "68vh", overflowY: "auto" }}>
                <HintBlock title="Что означает этот раздел" text={currentHint.what} />
                <HintBlock title="Зачем он нужен" text={currentHint.why} />
                <HintBlock title="Что сюда писать" text={currentHint.write} />
                {currentHint.formula && <HintBlock title="Формула" text={currentHint.formula} emphasis />}
                <div style={{ padding: "0.85rem", borderRadius: "var(--era-radius-md)", background: "var(--era-surface-2)" }}>
                  <strong style={{ display: "block", marginBottom: "0.4rem" }}>На какие вопросы ответить</strong>
                  <ul style={{ margin: 0, paddingLeft: "1.1rem", color: "var(--era-text-muted)", lineHeight: 1.55 }}>{currentHint.questions.map((item) => <li key={item}>{item}</li>)}</ul>
                </div>
                <HintBlock title="Как выглядит хороший ответ" text={currentHint.good} />
                <div style={{ padding: "0.85rem", borderRadius: "var(--era-radius-md)", background: "rgba(255,102,117,.06)", border: "1px solid rgba(255,102,117,.18)" }}>
                  <strong style={{ display: "block", marginBottom: "0.4rem" }}>Типичные ошибки</strong>
                  <ul style={{ margin: 0, paddingLeft: "1.1rem", color: "var(--era-text-muted)", lineHeight: 1.55 }}>{currentHint.mistakes.map((item) => <li key={item}>{item}</li>)}</ul>
                </div>
                <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.8rem", lineHeight: 1.5 }}>Разбор шага только объясняет логику. Он ничего не подставляет в ответ и не придумывает партнёров, людей, бюджет, показатели, результаты или цифры.</p>
              </div>
            </BottomSheet>
          )}
        </div>
      ) : (
        <>
          <Card style={constructorComplete ? { borderColor: "rgba(255,100,0,.28)" } : undefined}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem" }}>
              <div>
                <p style={{ margin: "0 0 .2rem", color: constructorComplete ? "var(--era-gold-ink)" : "var(--era-text-muted)", fontSize: ".72rem", fontWeight: 850, textTransform: "uppercase" }}>{constructorComplete ? "Финальный preview" : "Паспорт проекта"}</p>
                <strong style={{ fontSize: "var(--era-text-lg)" }}>{constructorComplete ? "Проверьте проект перед отправкой" : "Проект собирается"}</strong>
                <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>Заполнено {answeredQuestions.length} из {questions.length} шагов</p>
              </div>
              {project.can_edit && <button type="button" onClick={openEditor}>{answeredQuestions.length ? "Редактировать" : "Начать"}</button>}
            </div>
            {answeredQuestions.length === 0 ? <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)" }}>Пока есть только идея. Конструктор поможет превратить её в структуру проекта.</p> : (
              <div className="era-stagger" style={{ display: "flex", flexDirection: "column", gap: "0.9rem", marginTop: "0.85rem" }}>
                {answeredQuestions.map((question) => <div key={question.key}><p style={{ margin: 0, fontSize: "0.78rem", fontWeight: 750, color: "var(--era-text-muted)" }}>{question.title}</p><p style={{ margin: "0.25rem 0 0", whiteSpace: "pre-wrap", lineHeight: 1.45 }}>{answers[question.key]}</p></div>)}
              </div>
            )}
          </Card>

          {legacyAnswers.length > 0 && <Card><strong>Ранее заполненные данные</strong><p style={{ margin: ".25rem 0 .65rem", color: "var(--era-text-muted)", fontSize: ".8rem" }}>Старые поля сохранены и не потеряны.</p><div style={{ display: "flex", flexDirection: "column", gap: ".65rem" }}>{legacyAnswers.map(([key, value]) => <div key={key}><p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: ".76rem", fontWeight: 750 }}>{LEGACY_LABELS[key]}</p><p style={{ margin: ".2rem 0 0", whiteSpace: "pre-wrap" }}>{value}</p></div>)}</div></Card>}

          {project.can_edit && !constructorComplete && <button type="button" className="era-btn-primary" onClick={openEditor}>Продолжить конструктор</button>}
          {project.can_submit && <button type="button" className="era-btn-primary" disabled={busy || !constructorComplete} onClick={() => void handleSubmit()}>{busy ? "Отправляем…" : "Отправить на рассмотрение"}</button>}
          {project.can_delete && (
            <button type="button" disabled={busy} onClick={() => setDeleteOpen(true)} style={{ color: "var(--era-error)" }}>
              {isDraftLike ? "Удалить черновик" : "Убрать проект из моих"}
            </button>
          )}
          <button type="button" onClick={() => setShowWorkspace((value) => !value)}>{showWorkspace ? "Скрыть рабочую зону" : "Открыть рабочую зону →"}</button>
          {showWorkspace && <ProjectWorkspace projectId={projectId} />}
        </>
      )}

      <BottomSheet open={deleteOpen} onClose={() => setDeleteOpen(false)} title={isDraftLike ? "Удалить черновик?" : "Убрать проект?"}>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
          <p style={{ margin: 0, color: "var(--era-text-muted)", lineHeight: 1.55 }}>
            {isDraftLike
              ? "Черновик исчезнет из ваших проектов. Все сохранённые ответы этого черновика больше не будут доступны через интерфейс."
              : "Проект исчезнет из вашего рабочего списка. Это действие доступно только автору проекта в разрешённом статусе."}
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.55rem" }}>
            <button type="button" disabled={busy} onClick={() => setDeleteOpen(false)}>Оставить</button>
            <button type="button" disabled={busy} onClick={() => void handleDelete()} style={{ color: "var(--era-error)", borderColor: "rgba(255,102,117,.35)" }}>
              {busy ? "Удаляем…" : isDraftLike ? "Удалить черновик" : "Убрать"}
            </button>
          </div>
        </div>
      </BottomSheet>
    </div>
  );
}

function HintBlock({ title, text, emphasis = false }: { title: string; text: string; emphasis?: boolean }) {
  return (
    <div style={{ padding: "0.85rem", borderRadius: "var(--era-radius-md)", background: emphasis ? "var(--era-tint-violet)" : "var(--era-surface-2)", border: emphasis ? "1px solid rgba(99,44,255,.18)" : "1px solid var(--era-border)" }}>
      <strong style={{ display: "block", marginBottom: "0.3rem" }}>{title}</strong>
      <p style={{ margin: 0, color: emphasis ? "var(--era-text)" : "var(--era-text-muted)", lineHeight: 1.5 }}>{text}</p>
    </div>
  );
}
