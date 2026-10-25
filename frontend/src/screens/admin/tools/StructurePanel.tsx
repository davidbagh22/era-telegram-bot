import { useCallback, useState } from "react";
import { describeActionError, fetchDepartmentStructure, updateDepartmentDescription } from "../../../api/client";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { useAsync } from "../../../hooks/useAsync";

const inputStyle = {
  width: "100%",
  fontFamily: "var(--era-font-body)",
  padding: "0.5rem",
  borderRadius: "0.5rem",
  border: "1px solid var(--era-border)",
  background: "var(--era-bg)",
  color: "var(--era-text)",
} as const;

// Mini App equivalent of the bot's "🏛 Редактор структуры" flow
// (app/handlers/admin/management_ready.py) — see app/services/admin_structure_service.py.
// Only department descriptions are editable here, matching the bot's own
// scope: Direction.description exists on the model but was never exposed
// through this flow.
export function StructurePanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchDepartmentStructure(), [refreshKey]);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleSave = useCallback(
    async (departmentId: number) => {
      const draft = drafts[departmentId];
      if (draft === undefined) return;
      setBusyId(departmentId);
      setActionError(null);
      try {
        await updateDepartmentDescription(departmentId, draft);
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [drafts, refresh],
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}
      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить структуру." />}
      {state.status === "ready" && state.data.length === 0 && <EmptyState text="Департаментов пока нет." />}
      {state.status === "ready" &&
        state.data.map((department) => {
          const draft = drafts[department.id] ?? department.description ?? "";
          const changed = draft !== (department.description ?? "");
          return (
            <Card key={department.id}>
              <strong>{department.name}</strong>
              <textarea
                value={draft}
                onChange={(e) => setDrafts({ ...drafts, [department.id]: e.target.value })}
                rows={3}
                placeholder="Описание, которое видит участник"
                style={{ ...inputStyle, marginTop: "0.5rem" }}
              />
              <div style={{ marginTop: "0.5rem" }}>
                <button
                  type="button"
                  className="era-btn-primary"
                  disabled={!changed || busyId === department.id}
                  onClick={() => handleSave(department.id)}
                >
                  Сохранить
                </button>
              </div>
            </Card>
          );
        })}
    </div>
  );
}
