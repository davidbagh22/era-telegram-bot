import { useEffect, useState } from "react";
import { createProject, describeActionError, fetchProjects } from "../../api/client";
import { BottomSheet } from "../../components/BottomSheet";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { ProjectCard } from "../../components/ProjectCard";
import { SkeletonList } from "../../components/Skeleton";
import { FilterIcon, PlusIcon } from "../../components/icons";
import { useAsync } from "../../hooks/useAsync";
import type { ProjectScope } from "../../types/project";

const PROJECT_SCOPE_KEY = "era:projects:scope";
const SCOPES: { value: ProjectScope; label: string; description: string }[] = [
  { value: "mine", label: "Мои", description: "Ваши проекты и черновики" },
  { value: "open", label: "Открытые", description: "Проекты, куда можно включиться" },
  { value: "proposals", label: "На рассмотрении", description: "Проекты в процессе решения" },
  { value: "completed", label: "Завершённые", description: "Архив результатов" },
];

interface ProjectsListProps { onSelect: (projectId: number) => void; }

function initialScope(): ProjectScope {
  try {
    const value = window.sessionStorage.getItem(PROJECT_SCOPE_KEY) as ProjectScope | null;
    return SCOPES.some((option) => option.value === value) ? value! : "mine";
  } catch { return "mine"; }
}

export function ProjectsList({ onSelect }: ProjectsListProps) {
  const [scope, setScope] = useState<ProjectScope>(initialScope);
  const [showFilterSheet, setShowFilterSheet] = useState(false);
  const [idea, setIdea] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const state = useAsync(() => fetchProjects(scope), [scope]);
  const scopeConfig = SCOPES.find((option) => option.value === scope) ?? SCOPES[0];

  useEffect(() => {
    try { window.sessionStorage.setItem(PROJECT_SCOPE_KEY, scope); } catch { /* browser storage may be restricted */ }
  }, [scope]);

  const handleCreate = async () => {
    const draft = idea.trim();
    if (!draft || creating) return;
    setCreating(true);
    setCreateError(null);
    try {
      const project = await createProject(draft);
      setIdea("");
      onSelect(project.id);
    } catch (error) {
      setCreateError(describeActionError(error));
    } finally {
      setCreating(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <button type="button" onClick={() => setShowFilterSheet(true)} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%", padding: "0.7rem 0.85rem", background: "var(--era-surface)" }}>
        <span style={{ textAlign: "left" }}><strong>{scopeConfig.label}</strong><span style={{ display: "block", marginTop: 2, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 600 }}>{scopeConfig.description}</span></span>
        <FilterIcon width={20} height={20} style={{ color: "var(--era-red)" }} />
      </button>

      <BottomSheet open={showFilterSheet} onClose={() => setShowFilterSheet(false)} title="Какие проекты показать">
        <div style={{ display: "grid", gap: "0.45rem" }}>
          {SCOPES.map((option) => (
            <button key={option.value} type="button" onClick={() => { setScope(option.value); setShowFilterSheet(false); }} style={{ display: "flex", alignItems: "center", gap: "0.7rem", width: "100%", padding: "0.75rem", textAlign: "left", background: scope === option.value ? "var(--era-tint-red)" : "var(--era-surface)", borderColor: scope === option.value ? "rgba(227,38,54,.18)" : "var(--era-border)" }}>
              <input type="radio" readOnly checked={scope === option.value} />
              <span><strong>{option.label}</strong><span style={{ display: "block", marginTop: 2, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>{option.description}</span></span>
            </button>
          ))}
        </div>
      </BottomSheet>

      {scope === "mine" && (
        <Card style={{ borderColor: "rgba(227,38,54,.12)", background: "linear-gradient(145deg,rgba(227,38,54,.045),rgba(197,162,100,.04)),#fff" }}>
          <p className="era-kicker">Новый проект</p>
          <strong style={{ display: "block", marginTop: "0.3rem", fontSize: "var(--era-text-xl)" }}>Начните с одной мысли</strong>
          <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)" }}>Опишите идею одним предложением. После создания откроется конструктор из 16 шагов.</p>
          <textarea value={idea} onChange={(event) => { setIdea(event.target.value); setCreateError(null); }} placeholder="Мы делаем [что] для [кого], чтобы [зачем]" rows={3} style={{ marginTop: "0.75rem" }} />
          <button type="button" className="era-btn-primary" disabled={creating || !idea.trim()} onClick={() => void handleCreate()} style={{ width: "100%", marginTop: "0.65rem" }}>
            <PlusIcon width={19} height={19} />{creating ? "Создаю проект…" : "Начать конструктор"}
          </button>
          {createError && <p style={{ margin: "0.6rem 0 0", color: "var(--era-error)", fontSize: "var(--era-text-sm)" }}>Не получилось создать проект. {createError}</p>}
        </Card>
      )}

      {state.status === "loading" && <SkeletonList count={3} />}
      {state.status === "error" && <EmptyState title="Проекты не загрузились" description="Проверьте соединение и откройте раздел снова." />}
      {state.status === "ready" && state.data.length === 0 && (
        <EmptyState
          title={scope === "mine" ? "У вас пока нет проектов" : `В разделе «${scopeConfig.label}» пока пусто`}
          description={scope === "mine" ? "Создайте первую идею выше или посмотрите открытые проекты." : "Выберите другой фильтр — данные не скрываются за пустыми карточками."}
          actionLabel={scope === "mine" ? "Посмотреть открытые" : undefined}
          onAction={scope === "mine" ? () => setScope("open") : undefined}
        />
      )}
      {state.status === "ready" && <div style={{ display: "grid", gap: "0.75rem" }}>{state.data.map((project) => <ProjectCard key={project.id} project={project} onClick={() => onSelect(project.id)} />)}</div>}
    </div>
  );
}
