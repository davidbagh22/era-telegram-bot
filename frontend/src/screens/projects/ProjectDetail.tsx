import { useEffect, useMemo, useRef, useState } from "react";
import { cancelProject, describeActionError, fetchProject, submitProject, updateProject } from "../../api/client";
import { assistProjectAnswer, fetchProjectBuilderQuestions } from "../../api/projectBuilder";
import { BottomSheet } from "../../components/BottomSheet";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { PageHeader } from "../../components/PageHeader";
import { PrimaryButton, SecondaryButton } from "../../components/Buttons";
import { SkeletonList } from "../../components/Skeleton";
import { SparkIcon } from "../../components/icons";
import type { ProjectDetail as ProjectDetailType, ProjectQuestion } from "../../types/project";
import { projectStatusLabel } from "./statusLabels";
import { ProjectWorkspace } from "./ProjectWorkspace";

type AiOperation = "formulate" | "shorten" | "improve";
type SaveIntent = "next" | "close";
type AutosaveState = "idle" | "saving" | "saved" | "error";

type PendingRetry = {
  questionKey: string;
  questionIndex: number;
  answer: string;
  intent: SaveIntent;
};

interface ProjectDetailProps {
  projectId: number;
  onBack: () => void;
  initialShowWorkspace?: boolean;
}

const AUTOSAVE_DELAY = 700;

function draftKey(projectId: number): string { return `era:project:${projectId}:answers`; }

function readDraft(projectId: number): Record<string, string> {
  try {
    const raw = window.localStorage.getItem(draftKey(projectId));
    if (!raw) return {};
    const value = JSON.parse(raw) as unknown;
    if (!value || typeof value !== "object" || Array.isArray(value)) return {};
    return Object.fromEntries(Object.entries(value as Record<string, unknown>).filter(([, item]) => typeof item === "string")) as Record<string, string>;
  } catch { return {}; }
}

function writeDraft(projectId: number, answers: Record<string, string>): void {
  try { window.localStorage.setItem(draftKey(projectId), JSON.stringify(answers)); } catch { /* server save remains primary */ }
}

function clearDraft(projectId: number): void {
  try { window.localStorage.removeItem(draftKey(projectId)); } catch { /* ignore storage restrictions */ }
}

function firstUnansweredIndex(questions: ProjectQuestion[], answers: Record<string, string>): number {
  const index = questions.findIndex((question) => !(answers[question.key] ?? "").trim());
  return index >= 0 ? index : 0;
}

function humanError(error: unknown, fallback: string): string {
  const value = describeActionError(error);
  return value.startsWith("Не удалось выполнить действие") ? fallback : value;
}

export function ProjectDetail({ projectId, onBack, initialShowWorkspace = false }: ProjectDetailProps) {
  const [project, setProject] = useState<ProjectDetailType | null>(null);
  const [questions, setQuestions] = useState<ProjectQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [loadError, setLoadError] = useState(false);
  const [editing, setEditing] = useState(false);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const [showWorkspace, setShowWorkspace] = useState(initialShowWorkspace);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingRetry, setPendingRetry] = useState<PendingRetry | null>(null);
  const [autosave, setAutosave] = useState<AutosaveState>("idle");
  const [aiBusy, setAiBusy] = useState<AiOperation | null>(null);
  const [aiSuggestion, setAiSuggestion] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<"submit" | "cancel" | null>(null);
  const lastSavedRef = useRef<Record<string, string>>({});
  const autosaveSequence = useRef(0);

  useEffect(() => {
    let cancelled = false;
    setLoadError(false);
    Promise.all([fetchProject(projectId), fetchProjectBuilderQuestions()])
      .then(([projectData, questionData]) => {
        if (cancelled) return;
        const server = projectData.form_data ?? {};
        const local = readDraft(projectId);
        const merged = { ...server, ...local };
        lastSavedRef.current = { ...server };
        setProject(projectData);
        setQuestions(questionData);
        setAnswers(merged);
        writeDraft(projectId, merged);
        setQuestionIndex(firstUnansweredIndex(questionData, merged));
        const answered = questionData.filter((question) => (merged[question.key] ?? "").trim()).length;
        if (projectData.can_edit && answered <= 1) setEditing(true);
      })
      .catch(() => { if (!cancelled) setLoadError(true); });
    return () => { cancelled = true; };
  }, [projectId]);

  const currentQuestion = questions[questionIndex] ?? null;
  const currentAnswer = currentQuestion ? answers[currentQuestion.key] ?? "" : "";
  const answeredQuestions = useMemo(() => questions.filter((question) => (answers[question.key] ?? "").trim()), [answers, questions]);
  const complete = questions.length > 0 && answeredQuestions.length === questions.length;
  const progress = questions.length ? Math.round((answeredQuestions.length / questions.length) * 100) : 0;

  useEffect(() => {
    if (!editing || !currentQuestion || !project?.can_edit || busy) return;
    const value = currentAnswer;
    if (!value.trim() || value === (lastSavedRef.current[currentQuestion.key] ?? "")) {
      setAutosave("idle");
      return;
    }
    const sequence = ++autosaveSequence.current;
    setAutosave("saving");
    const timer = window.setTimeout(() => {
      updateProject(projectId, { [currentQuestion.key]: value })
        .then((updated) => {
          if (sequence !== autosaveSequence.current) return;
          lastSavedRef.current[currentQuestion.key] = updated.form_data?.[currentQuestion.key] ?? value;
          setProject(updated);
          setAutosave("saved");
          window.setTimeout(() => { if (sequence === autosaveSequence.current) setAutosave("idle"); }, 1300);
        })
        .catch(() => {
          if (sequence === autosaveSequence.current) setAutosave("error");
        });
    }, AUTOSAVE_DELAY);
    return () => window.clearTimeout(timer);
  }, [busy, currentAnswer, currentQuestion, editing, project?.can_edit, projectId]);

  if (loadError) return <><PageHeader title="Проект" onBack={onBack} /><EmptyState title="Проект не загрузился" description="Проверьте соединение. Черновик на этом устройстве не удалён." actionLabel="К проектам" onAction={onBack} /></>;
  if (!project) return <SkeletonList count={3} />;

  const setAnswer = (value: string) => {
    if (!currentQuestion) return;
    const next = { ...answers, [currentQuestion.key]: value };
    setAnswers(next);
    writeDraft(projectId, next);
    setPendingRetry((previous) => previous?.questionKey === currentQuestion.key ? { ...previous, answer: value } : previous);
    setActionError(null);
    setAiSuggestion(null);
  };

  const saveStep = async (question: ProjectQuestion, index: number, answer: string, intent: SaveIntent) => {
    if (!answer.trim()) { setActionError("Заполните этот шаг, чтобы продолжить."); return; }
    ++autosaveSequence.current;
    setBusy(true);
    setAutosave("saving");
    setActionError(null);
    try {
      const updated = await updateProject(projectId, { [question.key]: answer });
      const saved = updated.form_data?.[question.key] ?? answer;
      lastSavedRef.current[question.key] = saved;
      const nextAnswers = { ...answers, [question.key]: saved };
      setProject(updated);
      setAnswers(nextAnswers);
      writeDraft(projectId, nextAnswers);
      setPendingRetry(null);
      setAutosave("saved");
      setAiSuggestion(null);
      if (intent === "next") {
        if (index < questions.length - 1) setQuestionIndex(index + 1);
        else setEditing(false);
      } else setEditing(false);
    } catch (error) {
      setAutosave("error");
      setPendingRetry({ questionKey: question.key, questionIndex: index, answer, intent });
      setActionError(humanError(error, "Не удалось сохранить. Ваш ответ не потерян."));
    } finally { setBusy(false); }
  };

  const retry = async () => {
    if (!pendingRetry) return;
    const question = questions.find((item) => item.key === pendingRetry.questionKey);
    if (!question) return;
    await saveStep(question, pendingRetry.questionIndex, pendingRetry.answer, pendingRetry.intent);
  };

  const copyCurrentAnswer = async () => {
    const value = pendingRetry?.answer ?? currentAnswer;
    if (!value) return;
    try { await navigator.clipboard.writeText(value); setActionError("Ответ скопирован. Черновик также остаётся сохранён на устройстве."); }
    catch { setActionError("Не удалось скопировать автоматически. Текст остаётся в поле и в локальном черновике."); }
  };

  const runAi = async (operation: AiOperation) => {
    if (!currentQuestion || !currentAnswer.trim()) { setActionError("Сначала напишите свой вариант. ИИ улучшает ваш текст, а не придумывает факты вместо вас."); return; }
    setAiBusy(operation);
    setActionError(null);
    try { setAiSuggestion(await assistProjectAnswer(currentQuestion.key, currentAnswer.trim(), operation)); }
    catch (error) { setActionError(humanError(error, "ИИ-подсказка сейчас недоступна. Ваш текст не изменён.")); }
    finally { setAiBusy(null); }
  };

  const submit = async () => {
    if (!complete) { setActionError("Сначала завершите все 16 вопросов и проверьте preview."); return; }
    setBusy(true);
    setActionError(null);
    try {
      const updated = await submitProject(projectId);
      setProject(updated);
      setAnswers(updated.form_data ?? answers);
      clearDraft(projectId);
      setConfirmAction(null);
    } catch (error) { setActionError(humanError(error, "Не удалось отправить проект. Черновик сохранён, попробуйте снова.")); }
    finally { setBusy(false); }
  };

  const cancel = async () => {
    setBusy(true);
    setActionError(null);
    try { setProject(await cancelProject(projectId)); clearDraft(projectId); setConfirmAction(null); }
    catch (error) { setActionError(humanError(error, "Не удалось отменить проект.")); }
    finally { setBusy(false); }
  };

  const editQuestion = (index: number) => { setQuestionIndex(index); setEditing(true); setActionError(null); setPendingRetry(null); setAiSuggestion(null); };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <PageHeader title={project.title} eyebrow={`Проект · ${projectStatusLabel(project.status)}`} subtitle={project.short_description || undefined} onBack={onBack} />

      {project.admin_comment && <Card><p className="era-kicker">Комментарий команды</p><p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)" }}>{project.admin_comment}</p></Card>}
      {actionError && <Card style={{ borderColor: "rgba(101,90,115,.2)", background: "rgba(101,90,115,.05)" }}><strong>{autosave === "error" ? "Не удалось сохранить" : "Нужно действие"}</strong><p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)" }}>{actionError}</p>{pendingRetry && <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", marginTop: "0.75rem" }}><PrimaryButton busy={busy} busyLabel="Повторяем…" onClick={() => void retry()}>Попробовать снова</PrimaryButton><SecondaryButton onClick={() => void copyCurrentAnswer()}>Скопировать ответ</SecondaryButton></div>}</Card>}

      {editing && currentQuestion ? (
        <>
          <div><div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "center" }}><p className="era-kicker">{String(questionIndex + 1).padStart(2, "0")} / {questions.length}</p><span style={{ color: autosave === "error" ? "var(--era-error)" : "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>{autosave === "saving" ? "Сохраняем…" : autosave === "saved" ? "✓ Сохранено" : autosave === "error" ? "Не удалось сохранить · ответ не потерян" : "Черновик сохранён на устройстве"}</span></div><div style={{ height: 6, marginTop: "0.45rem", borderRadius: 999, background: "var(--era-ring-track)", overflow: "hidden" }}><div style={{ width: `${Math.max(progress, ((questionIndex + 1) / questions.length) * 100)}%`, height: "100%", background: "var(--era-red)", borderRadius: 999, transition: "width var(--era-motion)" }} /></div></div>

          <Card><p className="era-kicker">{currentQuestion.block}</p><h2 style={{ margin: "0.3rem 0 0", fontSize: "var(--era-text-2xl)" }}>{currentQuestion.title}</h2><p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)", whiteSpace: "pre-wrap", lineHeight: 1.55 }}>{currentQuestion.prompt}</p></Card>

          <Card>
            <label htmlFor={`project-answer-${currentQuestion.key}`} style={{ display: "block", fontWeight: 850, marginBottom: "0.5rem" }}>Ваш ответ</label>
            {currentQuestion.input_type === "text" ? <textarea id={`project-answer-${currentQuestion.key}`} value={currentAnswer} onChange={(event) => setAnswer(event.target.value)} rows={7} placeholder="Пишите своими словами — ответ сохраняется локально сразу" /> : <input id={`project-answer-${currentQuestion.key}`} type={currentQuestion.input_type} value={currentAnswer} onChange={(event) => setAnswer(event.target.value)} />}
          </Card>

          {currentQuestion.input_type === "text" && <Card style={{ background: "linear-gradient(145deg,rgba(227,38,54,.045),rgba(197,162,100,.055)),#fff", boxShadow: "none" }}><div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}><SparkIcon width={20} height={20} style={{ color: "var(--era-red)" }} /><strong>Помочь сформулировать</strong></div><p style={{ margin: "0.35rem 0 0.7rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>ИИ работает только с вашим текущим текстом и не добавляет выдуманные цифры, партнёров или результаты.</p><div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.45rem" }}><SecondaryButton disabled={aiBusy !== null} onClick={() => void runAi("formulate")}>{aiBusy === "formulate" ? "Формулирую…" : "Сформулировать"}</SecondaryButton><SecondaryButton disabled={aiBusy !== null} onClick={() => void runAi("shorten")}>{aiBusy === "shorten" ? "Сокращаю…" : "Сделать короче"}</SecondaryButton></div><SecondaryButton disabled={aiBusy !== null} onClick={() => void runAi("improve")} style={{ width: "100%", marginTop: "0.45rem" }}>{aiBusy === "improve" ? "Улучшаю…" : "Улучшить мой вариант"}</SecondaryButton>{currentQuestion.ai_hint && <p style={{ margin: "0.6rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>{currentQuestion.ai_hint}</p>}</Card>}

          {aiSuggestion && <Card style={{ borderColor: "rgba(197,162,100,.28)" }}><p className="era-kicker" style={{ color: "var(--era-gold-ink)" }}>Вариант ИИ — решение за вами</p><p style={{ whiteSpace: "pre-wrap" }}>{aiSuggestion}</p><div style={{ display: "grid", gridTemplateColumns: "1.2fr .8fr", gap: "0.5rem" }}><PrimaryButton onClick={() => { setAnswer(aiSuggestion); setAiSuggestion(null); }}>Использовать</PrimaryButton><SecondaryButton onClick={() => setAiSuggestion(null)}>Оставить мой</SecondaryButton></div></Card>}

          <div style={{ display: "grid", gridTemplateColumns: questionIndex > 0 ? "0.8fr 1.2fr" : "1fr", gap: "0.5rem" }}>
            {questionIndex > 0 && <SecondaryButton disabled={busy} onClick={() => { setQuestionIndex((value) => Math.max(0, value - 1)); setAiSuggestion(null); }}>Назад</SecondaryButton>}
            <PrimaryButton busy={busy} busyLabel="Сохраняем…" disabled={aiBusy !== null || !currentAnswer.trim()} onClick={() => void saveStep(currentQuestion, questionIndex, currentAnswer, "next")}>{questionIndex === questions.length - 1 ? "К финальному preview" : "Продолжить"}</PrimaryButton>
          </div>
          <SecondaryButton busy={busy} disabled={aiBusy !== null} onClick={() => currentAnswer.trim() ? void saveStep(currentQuestion, questionIndex, currentAnswer, "close") : setEditing(false)}>Сохранить и выйти</SecondaryButton>
        </>
      ) : (
        <>
          <Card>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "flex-start" }}><div><p className="era-kicker">{complete ? "Финальный preview" : "Паспорт проекта"}</p><strong style={{ display: "block", marginTop: "0.25rem", fontSize: "var(--era-text-lg)" }}>{complete ? "Проверьте все 16 разделов" : `Заполнено ${answeredQuestions.length} из ${questions.length}`}</strong></div>{project.can_edit && <SecondaryButton onClick={() => editQuestion(firstUnansweredIndex(questions, answers))}>{answeredQuestions.length ? "Продолжить" : "Начать"}</SecondaryButton>}</div>
            {answeredQuestions.length === 0 ? <p style={{ margin: "0.6rem 0 0", color: "var(--era-text-muted)" }}>Есть только идея. Откройте конструктор и соберите полноценный проект.</p> : <div style={{ display: "grid", gap: "0.9rem", marginTop: "1rem" }}>{answeredQuestions.map((question) => { const index = questions.findIndex((item) => item.key === question.key); return <div key={question.key} style={{ paddingTop: "0.8rem", borderTop: "1px solid var(--era-border)" }}><div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem" }}><strong>{question.title}</strong>{project.can_edit && <button type="button" className="era-btn-ghost" onClick={() => editQuestion(index)} style={{ minHeight: 36, padding: "0.25rem 0.5rem", color: "var(--era-red)" }}>Изменить</button>}</div><p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", whiteSpace: "pre-wrap" }}>{answers[question.key]}</p></div>; })}</div>}
          </Card>

          {project.can_submit && <PrimaryButton busy={busy} disabled={!complete} onClick={() => setConfirmAction("submit")}>Отправить на рассмотрение</PrimaryButton>}
          {project.can_edit && !complete && <PrimaryButton onClick={() => editQuestion(firstUnansweredIndex(questions, answers))}>Продолжить конструктор</PrimaryButton>}
          <SecondaryButton onClick={() => setShowWorkspace((value) => !value)}>{showWorkspace ? "Скрыть рабочую зону" : "Открыть команду и задачи"}</SecondaryButton>
          {showWorkspace && <ProjectWorkspace projectId={projectId} />}
          {project.can_delete && <button type="button" className="era-btn-danger" disabled={busy} onClick={() => setConfirmAction("cancel")}>Отменить проект</button>}
        </>
      )}

      <BottomSheet open={confirmAction === "submit"} onClose={() => setConfirmAction(null)} title="Отправить проект на рассмотрение?">
        <p style={{ margin: 0, color: "var(--era-text-muted)" }}>После отправки команда ЭРА увидит текущую версию всех 16 ответов. Вы получите статус проекта после решения.</p><div style={{ display: "grid", gridTemplateColumns: "0.8fr 1.2fr", gap: "0.5rem", marginTop: "1rem" }}><SecondaryButton onClick={() => setConfirmAction(null)}>Проверить ещё</SecondaryButton><PrimaryButton busy={busy} onClick={() => void submit()}>Отправить</PrimaryButton></div>
      </BottomSheet>
      <BottomSheet open={confirmAction === "cancel"} onClose={() => setConfirmAction(null)} title="Отменить проект?">
        <p style={{ margin: 0, color: "var(--era-text-muted)" }}>Это уберёт проект из активной работы. Действие требует подтверждения.</p><div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", marginTop: "1rem" }}><SecondaryButton onClick={() => setConfirmAction(null)}>Оставить</SecondaryButton><button type="button" className="era-btn-danger" disabled={busy} onClick={() => void cancel()}>{busy ? "Отменяем…" : "Отменить проект"}</button></div>
      </BottomSheet>
    </div>
  );
}
