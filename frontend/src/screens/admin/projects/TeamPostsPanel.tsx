import { useCallback, useState } from "react";
import {
  describeActionError,
  editTeamPost,
  fetchTeamPosts,
  prepareTeamPost,
  publishTeamPost,
  rejectTeamPost,
} from "../../../api/client";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";

const STATUS_LABELS: Record<string, string> = {
  pending: "Ждёт решения",
  edited: "Отредактировано, ждёт решения",
  prepared: "Одобрено, готово к публикации",
};

// The Mini App equivalent of app/handlers/admin/projects_block5_team.py —
// a project author's "looking for a team" text needs sign-off before it
// broadcasts to the general Telegram chat. Distinct from ProjectWorkspace's
// in-app roles/applications: this reaches people who aren't necessarily
// browsing the Mini App.
export function TeamPostsPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchTeamPosts(), [refreshKey]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const runAction = useCallback(
    async (projectId: number, action: () => Promise<unknown>) => {
      setBusyId(projectId);
      setActionError(null);
      try {
        await action();
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [refresh],
  );

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }
  if (state.status === "error") {
    return <EmptyState text="Не удалось загрузить публикации." />;
  }
  if (state.data.length === 0) {
    return <EmptyState text="Публикаций «ищем команду» на модерации нет." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}
      {state.data.map((post) => {
        const draft = drafts[post.project_id] ?? post.text;
        const isPrepared = post.status === "prepared";
        return (
          <Card key={post.project_id}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
              <strong>{post.project_title}</strong>
              <StatusBadge label={STATUS_LABELS[post.status] ?? post.status} tone="violet" />
            </div>
            <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
              Автор: {post.author_name}
            </p>
            <textarea
              value={draft}
              onChange={(event) =>
                setDrafts((previous) => ({ ...previous, [post.project_id]: event.target.value }))
              }
              rows={4}
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
              {draft !== post.text && (
                <button
                  type="button"
                  disabled={busyId === post.project_id}
                  onClick={() => runAction(post.project_id, () => editTeamPost(post.project_id, draft))}
                >
                  Сохранить правки
                </button>
              )}
              {!isPrepared && (
                <button
                  type="button"
                  className="era-btn-primary"
                  disabled={busyId === post.project_id}
                  onClick={() => runAction(post.project_id, () => prepareTeamPost(post.project_id))}
                >
                  Одобрить 1/2
                </button>
              )}
              {isPrepared && (
                <button
                  type="button"
                  className="era-btn-primary"
                  disabled={busyId === post.project_id}
                  onClick={() => runAction(post.project_id, () => publishTeamPost(post.project_id))}
                >
                  Опубликовать 2/2
                </button>
              )}
              <button
                type="button"
                disabled={busyId === post.project_id}
                onClick={() => runAction(post.project_id, () => rejectTeamPost(post.project_id))}
              >
                Отклонить
              </button>
            </div>
          </Card>
        );
      })}
    </div>
  );
}
