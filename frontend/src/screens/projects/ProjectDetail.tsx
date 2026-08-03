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

interface ProjectDetailProps {
  projectId: number;
  onBack: () => void;
}

export function ProjectDetail({ projectId, onBack }: ProjectDetailProps) {
  const [project, setProject] = useState<ProjectDetailType | null>(null);
  const [questions, setQuestions] = useState<ProjectQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" onClick={onBack}>
        ← К проектам
      </button>

      <Card>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <strong>{project.title}</strong>
          <StatusBadge label={project.status} tone="violet" />
        </div>
        {project.admin_comment && (
          <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)" }}>
            Комментарий: {project.admin_comment}
          </p>
        )}
      </Card>

      {project.can_edit && (
        <>
          <p style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem", margin: 0 }}>
            ИИ-подсказки для формулировок пока доступны только в боте — здесь можно
            редактировать готовые ответы.
          </p>
          {questions.map((question) => (
            <div key={question.key} style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
              <label style={{ fontSize: "0.8125rem", fontWeight: 600 }}>{question.title}</label>
              <textarea
                value={answers[question.key] ?? ""}
                onChange={(event) =>
                  setAnswers((previous) => ({ ...previous, [question.key]: event.target.value }))
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
          <button type="button" disabled={busy} onClick={handleSave}>
            Сохранить черновик
          </button>
        </>
      )}

      {project.can_submit && (
        <button type="button" disabled={busy} onClick={handleSubmit}>
          Отправить на рассмотрение
        </button>
      )}
      {project.can_delete && (
        <button type="button" disabled={busy} onClick={handleCancel}>
          Удалить проект
        </button>
      )}
    </div>
  );
}
