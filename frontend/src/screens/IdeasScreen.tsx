import { useState } from "react";
import { createProject, describeActionError, fetchProjects } from "../api/client";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { MonoLabel } from "../components/MonoLabel";
import { TypographyFeedCard } from "../components/TypographyFeedCard";
import { SkeletonList } from "../components/Skeleton";
import { useAsync } from "../hooks/useAsync";
import { formatProjectFeedDate } from "../utils/feedDate";
import { displayProjectTitle } from "./projects/displayTitle";

interface IdeasScreenProps {
  onOpenProject?: (projectId: number) => void;
  onBack?: () => void;
}

/** Ideas = project constructor entry + drafts — one clear path, not a new entity. */
export function IdeasScreen({ onOpenProject, onBack }: IdeasScreenProps) {
  const [idea, setIdea] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchProjects("mine"), [refreshKey]);

  const drafts = state.status === "ready"
    ? state.data.filter((project) => project.status === "draft" || project.status === "needs_revision")
    : [];

  const handleCreate = async () => {
    if (!idea.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      const project = await createProject(idea);
      setIdea("");
      onOpenProject?.(project.id);
    } catch (error) {
      setCreateError(describeActionError(error));
      setRefreshKey((value) => value + 1);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="era-page" style={{ padding: "1.15rem 1.15rem var(--era-page-bottom-safe)", display: "flex", flexDirection: "column", gap: "1.1rem" }}>
      {onBack && (
        <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>
          ← Орбита
        </button>
      )}
      <header>
        <MonoLabel>Орбита</MonoLabel>
        <h1 style={{ margin: "0.35rem 0 0", fontFamily: "var(--era-font-display)", fontSize: "1.8rem" }}>Идеи</h1>
        <p style={{ margin: "0.4rem 0 0", color: "var(--era-text-secondary)", fontSize: "0.9rem" }}>
          Одна мысль — и конструктор проведёт дальше. Не нужно заполнять всё сразу.
        </p>
      </header>

      <Card style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
        <strong>Новая идея</strong>
        <textarea
          value={idea}
          onChange={(event) => setIdea(event.target.value)}
          placeholder="Мы делаем [что] для [кого], чтобы [зачем]"
          rows={3}
        />
        <button type="button" className="era-btn-primary" disabled={creating || !idea.trim()} onClick={() => void handleCreate()}>
          {creating ? "Создаю…" : "Начать конструктор →"}
        </button>
        {createError && <p style={{ margin: 0, color: "var(--era-error)", fontSize: "0.85rem" }}>{createError}</p>}
      </Card>

      <section style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
        <MonoLabel>Черновики</MonoLabel>
        {state.status === "loading" && <SkeletonList count={2} />}
        {state.status === "error" && <EmptyState text="Не удалось загрузить черновики." />}
        {state.status === "ready" && drafts.length === 0 && (
          <EmptyState text="Черновиков пока нет — можно начать с одной мысли выше." />
        )}
        {drafts.map((project) => (
          <TypographyFeedCard
            key={project.id}
            title={displayProjectTitle(project.title)}
            dateLine={formatProjectFeedDate({
              proposedDate: project.proposed_date,
              proposedTime: project.proposed_time,
              dateIsTentative: project.date_is_tentative,
            })}
            onClick={() => onOpenProject?.(project.id)}
          />
        ))}
      </section>
    </div>
  );
}
