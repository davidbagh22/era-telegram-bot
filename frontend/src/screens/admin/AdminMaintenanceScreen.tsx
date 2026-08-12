import { useCallback, useState } from "react";
import { describeActionError, fetchMaintenancePreview, runMaintenanceReset } from "../../api/client";
import { Card } from "../../components/Card";
import { useAsync } from "../../hooks/useAsync";

const inputStyle = {
  width: "100%",
  fontFamily: "var(--era-font-body)",
  padding: "0.5rem",
  borderRadius: "0.5rem",
  border: "1px solid var(--era-border)",
  background: "var(--era-bg)",
  color: "var(--era-text)",
} as const;

const COUNT_LABELS: Record<string, string> = {
  users: "участников",
  events: "мероприятий",
  projects: "проектов",
  tasks: "заданий",
  points: "операций с баллами",
  portfolio_items: "записей портфолио",
  broadcasts: "рассылок",
  user_questions: "вопросов",
  audit_logs: "технических записей",
};

// Mini App equivalent of the bot's "🧹 Очистка тестовых данных" flow
// (app/handlers/admin/panel.py) — see app/services/maintenance_service.py.
// Deliberately restricted server-side to the ADMIN_IDS env var only (not
// any DB role=admin account, and not gated by the general admin-tools
// screens) — see require_maintenance_access in app/api/v1/admin.py. This
// is a per-user product decision, not a technical default: if you're
// tempted to widen who can see or use this, confirm with the owner first.
export function AdminMaintenanceScreen() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchMaintenancePreview(), [refreshKey]);
  const [confirming, setConfirming] = useState(false);
  const [phraseInput, setPhraseInput] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleReset = useCallback(async () => {
    if (state.status !== "ready") return;
    setRunning(true);
    setError(null);
    try {
      const outcome = await runMaintenanceReset(phraseInput);
      setResult(`Готово — удалено ${outcome.total} связанных тестовых записей.`);
      setConfirming(false);
      setPhraseInput("");
      setRefreshKey((key) => key + 1);
    } catch (err) {
      setError(describeActionError(err));
    } finally {
      setRunning(false);
    }
  }, [phraseInput, state]);

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }

  if (state.status === "error") {
    const message =
      state.detail === "maintenance_access_required"
        ? "Очистка доступна только основному администратору ЭРА."
        : "Не удалось загрузить данные для очистки.";
    return <Card>{message}</Card>;
  }

  const { counts, total, confirmation_phrase: confirmationPhrase } = state.data;
  const visible = Object.entries(counts).filter(([name]) => name in COUNT_LABELS);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <Card>
        <strong>🧹 Очистка тестовых данных</strong>
        <p style={{ margin: "0.5rem 0", color: "var(--era-text-muted)" }}>
          {visible.length > 0
            ? visible.map(([name, value]) => `${COUNT_LABELS[name]}: ${value}`).join(" · ")
            : "Рабочих данных для удаления нет"}
        </p>
        <p style={{ margin: "0 0 0.75rem" }}>Всего связанных записей: {total}</p>
        <p style={{ margin: "0 0 0.75rem", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
          Будут сохранены: основной администратор, департаменты, направления, бейджи, должности,
          ссылки, ID чатов и тексты приветствий.
        </p>

        {error && <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: "0 0 0.75rem" }}>{error}</p>}
        {result && (
          <p style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem", margin: "0 0 0.75rem" }}>{result}</p>
        )}

        {!confirming ? (
          <button type="button" disabled={total === 0} onClick={() => setConfirming(true)}>
            Продолжить очистку
          </button>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <p style={{ margin: 0, color: "var(--era-error)", fontWeight: 600 }}>Это действие нельзя отменить</p>
            <p style={{ margin: 0 }}>
              Чтобы удалить тестовых участников и всю рабочую историю, напишите точно:
              <br />
              <strong>{confirmationPhrase}</strong>
            </p>
            <input
              value={phraseInput}
              onChange={(e) => setPhraseInput(e.target.value)}
              placeholder={confirmationPhrase}
              style={inputStyle}
            />
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button
                type="button"
                disabled={running || phraseInput !== confirmationPhrase}
                onClick={handleReset}
              >
                Подтвердить и удалить
              </button>
              <button
                type="button"
                disabled={running}
                onClick={() => {
                  setConfirming(false);
                  setPhraseInput("");
                }}
              >
                Отмена
              </button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

