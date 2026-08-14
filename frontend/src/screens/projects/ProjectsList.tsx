import { useState } from "react";
import { createProject, describeActionError, fetchProjects } from "../../api/client";
import { BottomSheet } from "../../components/BottomSheet";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { useAsync } from "../../hooks/useAsync";
import type { ProjectScope } from "../../types/project";
import { projectStatusLabel } from "./statusLabels";

const SCOPES: { value: ProjectScope; label: string }[] = [
  { value: "mine", label: "Мои" },
  { value: "open", label: "Открытые" },
  { value: "proposals", label: "Предложения" },
  { value: "completed", label: "Завершённые" },
];

interface ProjectsListProps {
  onSelect: (projectId: number) => void;
}

export function ProjectsList({ onSelect }: ProjectsListProps) {
  const [scope, setScope] = useState<ProjectScope>("mine");
  const [showFilterSheet, setShowFilterSheet] = useState(false);
  const [idea, setIdea] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const state = useAsync(() => fetchProjects(scope), [scope]);
  const scopeLabel = SCOPES.find((option) => option.value === scope)?.label ?? scope;

  const handleCreate = async () => {
    setCreating(true);
    setCreateError(null);
    try {
      const project = await createProject(idea);
      setIdea("");
      onSelect(project.id);
    } catch (error) {
      setCreateError(describeActionError(error));
    } finally {
      setCreating(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {/* 2026-08 redesign brief section 15: no horizontal scope tabs as
          primary navigation — a single "Фильтр" button opens a bottom
          sheet instead, matching the pattern already used elsewhere
          (OpenTasksTab's destination picker, BroadcastPanel's audience
          picker). */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <strong>{scopeLabel}</strong>
        <button type="button" onClick={() => setShowFilterSheet(true)}>
          Фильтр
        </button>
      </div>

      <BottomSheet open={showFilterSheet} onClose={() => setShowFilterSheet(false)} title="Показать">
        <div style={{ display: "flex", flexDirection: "column" }}>
          {SCOPES.map((option) => (
            <button
              key={option.value}
              type="button"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                width: "100%",
                textAlign: "left",
                fontFamily: "var(--era-font-body)",
                fontSize: "0.9375rem",
                padding: "0.625rem 0.25rem",
                border: "none",
                borderBottom: "1px solid var(--era-border)",
                background: "transparent",
                color: "var(--era-text)",
              }}
              onClick={() => {
                setScope(option.value);
                setShowFilterSheet(false);
              }}
            >
              <input type="radio" readOnly checked={scope === option.value} />
              {option.label}
            </button>
          ))}
        </div>
      </BottomSheet>

      {scope === "mine" && (
        <Card>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <label style={{ fontSize: "0.8125rem", fontWeight: 600 }}>Новый проект</label>
            <textarea
              value={idea}
              onChange={(event) => setIdea(event.target.value)}
              placeholder="Мы делаем [что] для [кого], чтобы [зачем]"
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
            <button type="button" className="era-btn-primary" disabled={creating} onClick={handleCreate}>
              Создать черновик
            </button>
            {createError && (
              <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{createError}</p>
            )}
          </div>
        </Card>
      )}

      {state.status === "loading" && (
        <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>
      )}
      {state.status === "error" && <EmptyState text="Не удалось загрузить проекты." />}
      {state.status === "ready" && state.data.length === 0 && (
        <EmptyState text="Проектов в этом разделе пока нет." />
      )}
      {state.status === "ready" &&
        state.data.map((project) => (
          <Card key={project.id}>
            <button
              type="button"
              onClick={() => onSelect(project.id)}
              style={{
                all: "unset",
                cursor: "pointer",
                display: "block",
                width: "100%",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <strong>{project.title}</strong>
                <StatusBadge label={projectStatusLabel(project.status)} tone="violet" />
              </div>
              <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
                {project.short_description}
              </p>
            </button>
          </Card>
        ))}
    </div>
  );
}
