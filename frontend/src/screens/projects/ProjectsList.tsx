import { useState } from "react";
import { createProject, describeActionError, fetchProjects } from "../../api/client";
import { BottomSheet } from "../../components/BottomSheet";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { TypographyFeedCard } from "../../components/TypographyFeedCard";
import { useAsync } from "../../hooks/useAsync";
import type { ProjectScope } from "../../types/project";
import { formatProjectFeedDate } from "../../utils/feedDate";
import { displayProjectTitle } from "./displayTitle";


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
  const [scope, setScope] = useState<ProjectScope>(() => {
    try {
      const stored = sessionStorage.getItem("era.projects.scope");
      return SCOPES.some(s => s.value === stored) ? stored as ProjectScope : "open";
    } catch { return "open"; }
  });
  const [showFilterSheet, setShowFilterSheet] = useState(false);
  const [idea, setIdea] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const state = useAsync(() => fetchProjects(scope), [scope]);
  const scopeLabel = SCOPES.find((option) => option.value === scope)?.label ?? scope;

  const handleCreate = async () => {
    if (!idea.trim()) return;
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
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <strong>{scopeLabel}</strong>
        <button type="button" onClick={() => setShowFilterSheet(true)}>Фильтр</button>
      </div>

      <BottomSheet open={showFilterSheet} onClose={() => setShowFilterSheet(false)} title="Показать">
        <div style={{ display: "flex", flexDirection: "column" }}>
          {SCOPES.map((option) => (
            <button
              key={option.value}
              type="button"
              style={{ display: "flex", alignItems: "center", gap: "0.5rem", width: "100%", textAlign: "left", fontFamily: "var(--era-font-body)", fontSize: "0.9375rem", padding: "0.625rem 0.25rem", border: "none", borderBottom: "1px solid var(--era-border)", background: "transparent", color: "var(--era-text)" }}
              onClick={() => {
                setScope(option.value); setShowFilterSheet(false);
                try { sessionStorage.setItem("era.projects.scope", option.value); } catch { /* private mode */ }
              }}
            >
              <input type="radio" readOnly checked={scope === option.value} />
              {option.label}
            </button>
          ))}
        </div>
      </BottomSheet>

      {scope === "mine" && (
        <Card style={{ background: "linear-gradient(135deg, rgba(36,85,255,0.16), rgba(117,221,255,0.08)), var(--era-surface)" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
            <div>
              <p style={{ margin: "0 0 0.2rem", color: "var(--era-cyan)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Новый проект</p>
              <strong style={{ fontSize: "var(--era-text-xl)" }}>Начните с одной мысли</strong>
              <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", lineHeight: 1.45 }}>
                Не нужно заполнять проект целиком сейчас. Опишите идею одним предложением — дальше конструктор проведёт по аудитории, сценарию, команде, бюджету и продвижению.
              </p>
            </div>
            <textarea
              value={idea}
              onChange={(event) => setIdea(event.target.value)}
              placeholder="Мы делаем [что] для [кого], чтобы [зачем]"
              rows={3}
            />
            <button type="button" className="era-btn-primary" disabled={creating || !idea.trim()} onClick={handleCreate}>
              {creating ? "Создаю…" : "Начать конструктор →"}
            </button>
            {createError && <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{createError}</p>}
          </div>
        </Card>
      )}

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить проекты." actionLabel="Повторить" onAction={state.reload} />}
      {state.status === "ready" && state.data.length === 0 && <EmptyState text="Проектов в этом разделе пока нет." />}
      {state.status === "ready" && state.data.map((project) => (
          <TypographyFeedCard
            key={project.id}
            title={displayProjectTitle(project.title)}
            dateLine={formatProjectFeedDate({
              proposedDate: project.proposed_date,
              proposedTime: project.proposed_time,
              dateIsTentative: project.date_is_tentative,
            })}
            onClick={() => onSelect(project.id)}
          />
      ))}
    </div>
  );
}
