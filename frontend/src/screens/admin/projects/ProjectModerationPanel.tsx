import { useCallback, useState } from "react";
import { decideProject, describeActionError, fetchAdminProjects } from "../../../api/client";
import { BottomSheet } from "../../../components/BottomSheet";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";
import { projectStatusLabel } from "../../projects/statusLabels";
import type { ProjectDecisionAction, ProjectForModeration } from "../../../types/admin";

const DECISIONS: { action: ProjectDecisionAction; label: string; primary?: boolean }[] = [
  { action: "initial_accept", label: "Принять в работу", primary: true },
  { action: "venue_approve", label: "Одобрить", primary: true },
  { action: "revise", label: "На доработку" },
  { action: "postpone", label: "Перенести" },
  { action: "reject", label: "Отклонить" },
];

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

// 2026-08 UX/UI redesign brief section 13: the admin used to see a raw
// status enum, a comment box and all five decision buttons the instant
// the list rendered -- reads as a service CRM, not part of ЭРА. The list
// now shows a readable card per project ("Открыть →"); opening one shows
// the project's own content first, and "Принять решение" is a separate
// step that opens a bottom sheet rather than stacking every possible
// outcome under the description.
export function ProjectModerationPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAdminProjects(), [refreshKey]);
  const [openId, setOpenId] = useState<number | null>(null);
  const [showDecisionSheet, setShowDecisionSheet] = useState(false);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleDecide = useCallback(
    async (projectId: number, action: ProjectDecisionAction) => {
      const trimmed = comment.trim();
      if (!trimmed) return;
      setBusy(true);
      setActionError(null);
      try {
        await decideProject(projectId, action, trimmed);
        setComment("");
        setShowDecisionSheet(false);
        setOpenId(null);
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusy(false);
      }
    },
    [comment, refresh],
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

  const open = state.data.find((project) => project.id === openId) ?? null;

  if (open) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <button type="button" onClick={() => setOpenId(null)}>
          ← К проектам на рассмотрении
        </button>
        {actionError && (
          <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
        )}
        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
            <strong style={{ fontFamily: "var(--era-font-display)", fontSize: "var(--era-text-xl)" }}>
              {open.title}
            </strong>
            <StatusBadge label={projectStatusLabel(open.status)} tone="violet" />
          </div>
          <p style={{ margin: "0.5rem 0 0", fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>
            Подан {formatDate(open.submitted_at)}
          </p>
          {open.short_description && <p style={{ margin: "0.5rem 0 0" }}>{open.short_description}</p>}
          {open.admin_comment && (
            <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)" }}>
              Предыдущий комментарий: {open.admin_comment}
            </p>
          )}
        </Card>
        <button type="button" className="era-btn-primary" onClick={() => setShowDecisionSheet(true)}>
          Принять решение
        </button>

        <BottomSheet
          open={showDecisionSheet}
          onClose={() => setShowDecisionSheet(false)}
          title="Решение по проекту"
        >
          <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
            <textarea
              placeholder="Комментарий автору (обязателен для решения)"
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              rows={2}
              style={{
                width: "100%",
                fontFamily: "var(--era-font-body)",
                padding: "0.5rem",
                borderRadius: "0.5rem",
                border: "1px solid var(--era-border)",
                background: "var(--era-bg)",
                color: "var(--era-text)",
              }}
            />
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              {DECISIONS.map(({ action, label, primary }) => (
                <button
                  key={action}
                  type="button"
                  className={primary ? "era-btn-primary" : undefined}
                  disabled={busy || !comment.trim()}
                  onClick={() => handleDecide(open.id, action)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </BottomSheet>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {state.data.map((project: ProjectForModeration) => (
        <Card key={project.id}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
            <strong>{project.title}</strong>
            <StatusBadge label={projectStatusLabel(project.status)} tone="violet" />
          </div>
          {project.short_description && (
            <p style={{ margin: "0.375rem 0 0", color: "var(--era-text-muted)" }}>
              {project.short_description}
            </p>
          )}
          <p style={{ margin: "0.375rem 0 0.5rem", fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>
            Подан {formatDate(project.submitted_at)}
          </p>
          <button
            type="button"
            onClick={() => {
              setComment("");
              setOpenId(project.id);
            }}
          >
            Открыть →
          </button>
        </Card>
      ))}
    </div>
  );
}
