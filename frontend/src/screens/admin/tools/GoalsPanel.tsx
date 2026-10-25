import { useCallback, useState } from "react";
import { createGoal, decideGoal, describeActionError, fetchAdminGoals } from "../../../api/client";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
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

// Mini App equivalent of the bot's "🎯 Ежемесячные цели" flow
// (app/handlers/admin/management_ready.py) — see app/services/admin_goals_service.py.
export function GoalsPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAdminGoals(), [refreshKey]);
  const [title, setTitle] = useState("");
  const [targetValue, setTargetValue] = useState("1");
  const [month, setMonth] = useState("");
  const [scopeQuery, setScopeQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleCreate = useCallback(async () => {
    const parsedTarget = Number(targetValue);
    if (!title.trim() || !Number.isFinite(parsedTarget) || parsedTarget <= 0) return;
    setCreating(true);
    setActionError(null);
    try {
      await createGoal({
        title: title.trim(),
        target_value: parsedTarget,
        month: month.trim() || null,
        scope_query: scopeQuery.trim() || null,
      });
      setTitle("");
      setTargetValue("1");
      setMonth("");
      setScopeQuery("");
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setCreating(false);
    }
  }, [title, targetValue, month, scopeQuery, refresh]);

  const runAction = useCallback(
    async (goalId: number, action: "inc" | "done" | "delete") => {
      setBusyId(goalId);
      setActionError(null);
      try {
        await decideGoal(goalId, action);
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [refresh],
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}
      <Card>
        <strong>Новая цель</strong>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
          <input placeholder="Название цели" value={title} onChange={(e) => setTitle(e.target.value)} style={inputStyle} />
          <input
            placeholder="План (число)"
            value={targetValue}
            onChange={(e) => setTargetValue(e.target.value)}
            inputMode="numeric"
            style={inputStyle}
          />
          <input
            placeholder="Месяц ГГГГ-ММ (необязательно — по умолчанию текущий)"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            style={inputStyle}
          />
          <input
            placeholder="Департамент/направление (необязательно — иначе общая цель)"
            value={scopeQuery}
            onChange={(e) => setScopeQuery(e.target.value)}
            style={inputStyle}
          />
          <button
            type="button"
            className="era-btn-primary"
            disabled={creating || !title.trim()}
            onClick={handleCreate}
          >
            Добавить цель
          </button>
        </div>
      </Card>

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить цели." />}
      {state.status === "ready" && state.data.length === 0 && <EmptyState text="Пока целей нет." />}
      {state.status === "ready" &&
        state.data.map((goal) => (
          <Card key={goal.id}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
              <strong>{goal.title}</strong>
              <StatusBadge
                label={goal.status === "done" ? "готово" : `${goal.current_value}/${goal.target_value}`}
                tone={goal.status === "done" ? "violet" : "neutral"}
              />
            </div>
            <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>
              {goal.month} · {goal.scope_name ?? "Общая цель"}
            </p>
            {goal.status !== "done" && (
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button type="button" disabled={busyId === goal.id} onClick={() => runAction(goal.id, "inc")}>
                  +1
                </button>
                <button type="button" disabled={busyId === goal.id} onClick={() => runAction(goal.id, "done")}>
                  Готово
                </button>
                <button type="button" disabled={busyId === goal.id} onClick={() => runAction(goal.id, "delete")}>
                  Удалить
                </button>
              </div>
            )}
          </Card>
        ))}
    </div>
  );
}
