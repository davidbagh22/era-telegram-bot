import { useCallback, useState } from "react";
import { describeActionError, fetchChatGreetings, toggleChatGreeting, updateChatGreetingText } from "../../../api/client";
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

// Mini App equivalent of the bot's "👋 Автоматические приветствия" flow
// (app/handlers/admin/panel.py) — see app/services/admin_greetings_service.py.
// Covers exactly the bot's scope: toggle on/off + edit text (with {name}
// placeholder support) for the 4 attached chats. Title stays fixed/seeded —
// the bot never let admins rename a greeting either.
export function GreetingsPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchChatGreetings(), [refreshKey]);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleSaveText = useCallback(
    async (greetingId: number) => {
      const draft = drafts[greetingId];
      if (draft === undefined || !draft.trim()) return;
      setBusyId(greetingId);
      setActionError(null);
      try {
        await updateChatGreetingText(greetingId, draft.trim());
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [drafts, refresh],
  );

  const handleToggle = useCallback(
    async (greetingId: number) => {
      setBusyId(greetingId);
      setActionError(null);
      try {
        await toggleChatGreeting(greetingId);
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
      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить приветствия." />}
      {state.status === "ready" && state.data.length === 0 && <EmptyState text="Приветствий пока нет." />}
      {state.status === "ready" &&
        state.data.map((greeting) => {
          const draft = drafts[greeting.id] ?? greeting.text;
          const changed = draft !== greeting.text;
          return (
            <Card key={greeting.id}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
                <strong>{greeting.title}</strong>
                <StatusBadge
                  label={greeting.is_enabled ? "включено" : "выключено"}
                  tone={greeting.is_enabled ? "violet" : "neutral"}
                />
              </div>
              {!greeting.is_bound && (
                <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
                  Чат ещё не привязан — перешлите любое сообщение из него боту с /bind
                </p>
              )}
              <textarea
                value={draft}
                onChange={(e) => setDrafts({ ...drafts, [greeting.id]: e.target.value })}
                rows={3}
                placeholder="Можно использовать {name} — бот подставит имя нового участника"
                style={{ ...inputStyle, marginTop: "0.5rem" }}
              />
              <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem" }}>
                <button
                  type="button"
                  className="era-btn-primary"
                  disabled={!changed || busyId === greeting.id}
                  onClick={() => handleSaveText(greeting.id)}
                >
                  Сохранить текст
                </button>
                <button type="button" disabled={busyId === greeting.id} onClick={() => handleToggle(greeting.id)}>
                  {greeting.is_enabled ? "Отключить" : "Включить"}
                </button>
              </div>
            </Card>
          );
        })}
    </div>
  );
}
