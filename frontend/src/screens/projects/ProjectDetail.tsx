import { useEffect, useState } from "react";
import {
  cancelProject,
  fetchProject,
  fetchProjectQuestions,
  submitProject,
  updateProject,
} from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import type { ProjectDetail as ProjectDetailType, ProjectQuestion } from "../../types/project";
import { projectStatusLabel } from "./statusLabels";
import { ProjectWorkspace } from "./ProjectWorkspace";

interface ProjectDetailProps {
  projectId: number;
  onBack: () => void;
  /** Deep links (e.g. from a task/event notification) want to land the
   * viewer straight in the collaborative workspace rather than the
   * project's own read view. */
  initialShowWorkspace?: boolean;
}

// 2026-08 UX/UI redesign brief sections 8-11: a project must always be
// readable once the viewer can see it at all -- previously the entire
// "Форма" tab (the only place project content rendered) was gated behind
// `can_edit`, so a project sitting in initial_review after submission
// showed nothing but the header card and an empty tab. View and edit are
// now two different concerns: this screen always shows the saved answers;
// a separate "Редактировать" toggle (visible only when can_edit) is the
// one place editing happens. "Форма"/"Workspace" as competing top-level
// tabs are retired too -- the workspace is a secondary action below the
// project's own content, not an equal alternative to it.
export function ProjectDetail({ projectId, onBack, initialShowWorkspace = false }: ProjectDetailProps) {
  const [project, setProject] = useState<ProjectDetailType | null>(null);
  const [questions, setQuestions] = useState<ProjectQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [showWorkspace, setShowWorkspace] = useState(initialShowWorkspace);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchProject(projectId), fetchProjectQuestions()])
      .then(([projectData, questionData]) => {
        if (cancelled) return;
        setProject(projectData);
        setQuestions(questionData);
        setAnswers(projectData.form_data);
      })
      .catch(() => {
        if (!cancelled) setError("Не удалось загрузить проект.");
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  if (error) {
    return <EmptyState text={error} />;
  }
  if (!project) {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }

  const handleSave = async () => {
    setBusy(true);
    try {
      const updated = await updateProject(projectId, answers);
      setProject(updated);
      setEditing(false);
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
    } finally {
      setBusy(false);
    }
  };

  const answeredQuestions = questions.filter((question) => (answers[question.key] ?? "").trim());

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" onClick={onBack}>
        ← К проектам
      </button>

      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
          <strong style={{ fontFamily: "var(--era-font-display)", fontSize: "var(--era-text-xl)" }}>
            {project.title}
          </strong>
          <StatusBadge label={projectStatusLabel(project.status)} tone="violet" />
        </div>
        {project.short_description && (
          <p style={{ margin: "0.5rem 0 0" }}>{project.short_description}</p>
        )}
        {project.admin_comment && (
          <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)" }}>
            Комментарий команды ЭРА: {project.admin_comment}
          </p>
        )}
      </Card>

      {!editing ? (
        <>
          <Card>
            <strong style={{ fontSize: "var(--era-text-lg)" }}>О проекте</strong>
            {answeredQuestions.length === 0 ? (
              <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)" }}>
                Ответы пока не заполнены.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginTop: "0.5rem" }}>
                {answeredQuestions.map((question) => (
                  <div key={question.key}>
                    <p style={{ margin: 0, fontSize: "0.8125rem", fontWeight: 600, color: "var(--era-text-muted)" }}>
                      {question.title}
                    </p>
                    <p style={{ margin: "0.25rem 0 0", whiteSpace: "pre-wrap" }}>{answers[question.key]}</p>
                  </div>
                ))}
              </div>
            )}
            {project.can_edit && (
              <button type="button" style={{ marginTop: "0.75rem" }} onClick={() => setEditing(true)}>
                Редактировать
              </button>
            )}
          </Card>

          {project.can_submit && (
            <button type="button" className="era-btn-primary" disabled={busy} onClick={handleSubmit}>
              Отправить на рассмотрение
            </button>
          )}
          {project.can_delete && (
            <button type="button" disabled={busy} onClick={handleCancel}>
              Удалить проект
            </button>
          )}

          <button type="button" onClick={() => setShowWorkspace((value) => !value)}>
            {showWorkspace ? "Скрыть рабочее пространство" : "Рабочее пространство →"}
          </button>
          {showWorkspace && <ProjectWorkspace projectId={projectId} />}
        </>
      ) : (
        <Card>
          <strong style={{ fontSize: "var(--era-text-lg)" }}>Редактирование</strong>
          <p style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem", margin: "0.25rem 0 0.75rem" }}>
            ИИ-подсказки для формулировок пока доступны только в боте — здесь можно
            редактировать готовые ответы.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {questions.map((question) => (
              <div key={question.key} style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                <label style={{ fontSize: "0.8125rem", fontWeight: 600 }}>{question.title}</label>
                <textarea
                  value={answers[question.key] ?? ""}
                  onChange={(event) =>
                    setAnswers((previous) => ({
                      ...previous,
                      [question.key]: event.target.value,
                    }))
                  }
                  rows={2}
                  style={{
                    fontFamily: "var(--era-font-body)",
                    padding: "0.5rem",
                    borderRadius: "0.5rem",
                    border: "1px solid var(--era-border)",
                    background: "var(--era-bg)",
                    color: "var(--era-text)",
                  }}
                />
              </div>
            ))}
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button type="button" className="era-btn-primary" disabled={busy} onClick={handleSave}>
                Сохранить
              </button>
              <button type="button" disabled={busy} onClick={() => setEditing(false)}>
                Отмена
              </button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
