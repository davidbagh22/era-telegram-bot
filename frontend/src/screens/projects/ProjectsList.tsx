import { useState } from "react";
import { createProject, describeActionError, fetchProjects } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { SegmentedTabs } from "../../components/SegmentedTabs";
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
  const [idea, setIdea] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const state = useAsync(() => fetchProjects(scope), [scope]);

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
      <SegmentedTabs options={SCOPES} active={scope} onChange={setScope} />

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
