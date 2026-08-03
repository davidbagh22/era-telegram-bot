import { useCallback, useState } from "react";
import { decideProject, fetchAdminProjects } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { useAsync } from "../../hooks/useAsync";
import type { ProjectDecisionAction } from "../../types/admin";

const DECISIONS: { action: ProjectDecisionAction; label: string }[] = [
  { action: "initial_accept", label: "Принять в работу" },
  { action: "venue_approve", label: "Одобрить" },
  { action: "revise", label: "На доработку" },
  { action: "postpone", label: "Перенести" },
  { action: "reject", label: "Отклонить" },
];

export function AdminProjectsScreen() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAdminProjects(), [refreshKey]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [comments, setComments] = useState<Record<number, string>>({});

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleDecide = useCallback(
    async (projectId: number, action: ProjectDecisionAction) => {
      const comment = (comments[projectId] ?? "").trim();
      if (!comment) return;
      setBusyId(projectId);
      try {
        await decideProject(projectId, action, comment);
        refresh();
      } finally {
        setBusyId(null);
      }
    },
    [comments, refresh],
  );

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }
  if (state.status === "error") {
    return <EmptyState text="Не удалось загрузить проекты." />;
  }
  if (state.data.length === 0) {
    return <EmptyState text="Проектов на рассмотрении нет." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {state.data.map((project) => (
        <Card key={project.id}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <strong>{project.title}</strong>
            <StatusBadge label={project.status} tone="violet" />
          </div>
          <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>
            {project.short_description}
          </p>
          <textarea
            placeholder="Комментарий автору (обязателен для решения)"
            value={comments[project.id] ?? ""}
            onChange={(event) =>
              setComments((previous) => ({ ...previous, [project.id]: event.target.value }))
            }
            rows={2}
            style={{
              width: "100%",
              fontFamily: "var(--era-font-body)",
              padding: "0.5rem",
              borderRadius: "0.5rem",
              border: "1px solid var(--era-border)",
              background: "var(--era-bg)",
              color: "var(--era-text)",
              marginBottom: "0.5rem",
            }}
          />
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            {DECISIONS.map(({ action, label }) => (
              <button
                key={action}
                type="button"
                disabled={busyId === project.id}
                onClick={() => handleDecide(project.id, action)}
              >
                {label}
              </button>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}
