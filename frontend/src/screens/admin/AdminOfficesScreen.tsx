import { useCallback, useState } from "react";
import {
  assignOffice,
  createOffice,
  deleteOffice,
  describeActionError,
  fetchAdminOffices,
  removeOfficeAssignment,
  searchAssignableUsers,
} from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { useAsync } from "../../hooks/useAsync";
import type { UserListItem } from "../../types/admin";

const inputStyle = {
  width: "100%",
  fontFamily: "var(--era-font-body)",
  padding: "0.5rem",
  borderRadius: "0.5rem",
  border: "1px solid var(--era-border)",
  background: "var(--era-bg)",
  color: "var(--era-text)",
} as const;

// "Должности и ответственность" — the Mini App equivalent of
// app/handlers/admin/offices_management.py (list/view/delete) and the
// office_assign/office_remove/office_new handlers in panel.py.
export function AdminOfficesScreen() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAdminOffices(), [refreshKey]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [assigningOfficeId, setAssigningOfficeId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState<UserListItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleCreate = useCallback(async () => {
    if (!title.trim()) return;
    setCreating(true);
    setActionError(null);
    try {
      await createOffice(title.trim(), description.trim());
      setTitle("");
      setDescription("");
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setCreating(false);
    }
  }, [title, description, refresh]);

  const runAction = useCallback(
    async (officeId: number, action: () => Promise<unknown>) => {
      setBusyId(officeId);
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

  const startAssigning = useCallback((officeId: number) => {
    setAssigningOfficeId(officeId);
    setQuery("");
    setCandidates([]);
  }, []);

  const handleSearch = useCallback(async () => {
    if (!query.trim()) return;
    setSearching(true);
    setActionError(null);
    try {
      setCandidates(await searchAssignableUsers(query.trim()));
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setSearching(false);
    }
  }, [query]);

  const handleAssign = useCallback(
    async (officeId: number, userId: number) => {
      await runAction(officeId, () => assignOffice(officeId, userId));
      setAssigningOfficeId(null);
    },
    [runAction],
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}
      <Card>
        <strong>Новая должность</strong>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
          <input placeholder="Название" value={title} onChange={(e) => setTitle(e.target.value)} style={inputStyle} />
          <textarea
            placeholder="Ответственность (необязательно)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            style={inputStyle}
          />
          <button type="button" className="era-btn-primary" disabled={creating || !title.trim()} onClick={handleCreate}>
            Добавить должность
          </button>
        </div>
      </Card>

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить должности." />}
      {state.status === "ready" && state.data.length === 0 && <EmptyState text="Должностей пока нет." />}
      {state.status === "ready" &&
        state.data.map((office) => (
          <Card key={office.id}>
            <strong>{office.title}</strong>
            {office.description && (
              <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>{office.description}</p>
            )}
            <p style={{ margin: "0.25rem 0 0.5rem", fontSize: "0.875rem" }}>
              Сейчас:{" "}
              {office.assignments.length === 0
                ? "никто не назначен"
                : office.assignments.map((assignment) => (
                    <span key={assignment.assignment_id} style={{ marginRight: "0.5rem" }}>
                      {assignment.user_name}{" "}
                      <button
                        type="button"
                        disabled={busyId === office.id}
                        onClick={() => runAction(office.id, () => removeOfficeAssignment(assignment.assignment_id))}
                        style={{ minHeight: "auto", padding: "0.125rem 0.5rem", fontSize: "0.75rem" }}
                      >
                        Завершить
                      </button>
                    </span>
                  ))}
            </p>

            {assigningOfficeId === office.id ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <input
                    placeholder="Имя, username или Telegram ID"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    style={{ ...inputStyle, flex: 1 }}
                  />
                  <button type="button" disabled={searching || !query.trim()} onClick={handleSearch}>
                    Найти
                  </button>
                </div>
                {candidates.map((candidate) => (
                  <button
                    key={candidate.id}
                    type="button"
                    onClick={() => handleAssign(office.id, candidate.id)}
                    style={{ textAlign: "left" }}
                  >
                    {candidate.first_name} {candidate.last_name ?? ""}
                  </button>
                ))}
                <button type="button" onClick={() => setAssigningOfficeId(null)}>
                  Отмена
                </button>
              </div>
            ) : (
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button type="button" disabled={busyId === office.id} onClick={() => startAssigning(office.id)}>
                  Назначить человека
                </button>
                <button
                  type="button"
                  disabled={busyId === office.id}
                  onClick={() => runAction(office.id, () => deleteOffice(office.id))}
                >
                  Удалить должность
                </button>
              </div>
            )}
          </Card>
        ))}
    </div>
  );
}
