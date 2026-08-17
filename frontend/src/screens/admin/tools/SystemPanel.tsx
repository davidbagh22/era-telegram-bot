import { useCallback, useState } from "react";
import { fetchSystemSnapshot, runSystemDiagnostic } from "../../../api/systemClient";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { useAsync } from "../../../hooks/useAsync";

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function statusLabel(value: string): string {
  if (value === "healthy" || value === "ok" || value === "success") return "в порядке";
  if (value === "degraded" || value === "warning") return "требует внимания";
  if (value === "critical" || value === "error" || value === "failed") return "критично";
  if (value === "open") return "открыт";
  if (value === "resolved") return "закрыт";
  return value;
}

export function SystemPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchSystemSnapshot(), [refreshKey]);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((value) => value + 1), []);

  const runFull = useCallback(async () => {
    setRunning(true);
    setError(null);
    setMessage(null);
    try {
      const result = await runSystemDiagnostic("full");
      setMessage(`Диагностика завершена: ${result.score}/100 · ${statusLabel(result.status)}`);
      refresh();
    } catch {
      setError("Не удалось запустить диагностику. Проверьте состояние API и права администратора.");
    } finally {
      setRunning(false);
    }
  }, [refresh]);

  const copyPrompt = useCallback(async (prompt: string | null) => {
    if (!prompt) return;
    try {
      await navigator.clipboard.writeText(prompt);
      setMessage("Промпт для исправления скопирован");
    } catch {
      setError("Не удалось скопировать промпт. Откройте ЭРА в актуальной версии Telegram.");
    }
  }, []);

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Проверяем состояние системы…</p>;
  }
  if (state.status === "error") {
    return <EmptyState text="Не удалось загрузить состояние системы." />;
  }

  const { latest, latest_full: latestFull, incidents, backups } = state.data;
  const openIncidents = incidents.filter((item) => item.status === "open");
  const recentIncidents = incidents.slice(0, 12);
  const latestBackup = backups[0] ?? null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", minWidth: 0 }}>
      <Card gradient>
        <p style={{ margin: 0, color: "var(--era-text-secondary)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
          Здоровье ЭРА
        </p>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "flex-end", marginTop: "0.5rem" }}>
          <div>
            <strong style={{ fontSize: "var(--era-text-4xl)" }}>{latest?.score ?? "—"}</strong>
            <span style={{ color: "var(--era-text-secondary)" }}>/100</span>
          </div>
          <strong>{latest ? statusLabel(latest.status) : "нет данных"}</strong>
        </div>
        <p style={{ margin: "0.6rem 0 0", color: "var(--era-text-secondary)", fontSize: "var(--era-text-sm)" }}>
          Heartbeat: {formatDate(latest?.created_at)} · Full: {formatDate(latestFull?.created_at)}
        </p>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.75rem" }}>
        <Card>
          <strong style={{ fontSize: "var(--era-text-2xl)" }}>{openIncidents.length}</strong>
          <span style={{ display: "block", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>открытых инцидентов</span>
        </Card>
        <Card>
          <strong style={{ fontSize: "var(--era-text-lg)" }}>{latestBackup ? statusLabel(latestBackup.status) : "нет данных"}</strong>
          <span style={{ display: "block", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>последний backup</span>
        </Card>
      </div>

      <button type="button" disabled={running} onClick={runFull}>
        {running ? "Диагностика выполняется…" : "Запустить полную диагностику"}
      </button>
      {message && <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>{message}</p>}
      {error && <p style={{ margin: 0, color: "var(--era-error)", fontSize: "var(--era-text-sm)" }}>{error}</p>}

      <section>
        <h3 style={{ margin: "0.25rem 0 0.65rem" }}>Проверки</h3>
        {!latest || latest.checks.length === 0 ? (
          <EmptyState text="Диагностика ещё не запускалась." />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {latest.checks.map((check) => (
              <Card key={check.key}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem" }}>
                  <strong>{check.title}</strong>
                  <span style={{ color: check.status === "ok" ? "var(--era-success)" : "var(--era-error)", fontSize: "var(--era-text-xs)", fontWeight: 800 }}>
                    {statusLabel(check.status)}
                  </span>
                </div>
                <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>{check.detail}</p>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section>
        <h3 style={{ margin: "0.25rem 0 0.65rem" }}>Инциденты</h3>
        {recentIncidents.length === 0 ? (
          <EmptyState text="Инцидентов нет." />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {recentIncidents.map((incident) => (
              <Card key={incident.id}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem" }}>
                  <strong>{incident.title}</strong>
                  <span style={{ color: incident.status === "open" ? "var(--era-error)" : "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800 }}>
                    {statusLabel(incident.status)}
                  </span>
                </div>
                <p style={{ margin: "0.35rem 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>{incident.detail}</p>
                <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>
                  {incident.severity} · повторов: {incident.occurrence_count} · {formatDate(incident.last_seen_at)}
                </p>
                {incident.status === "open" && incident.fix_prompt && (
                  <button type="button" onClick={() => copyPrompt(incident.fix_prompt)} style={{ marginTop: "0.55rem" }}>
                    Скопировать промпт для исправления
                  </button>
                )}
              </Card>
            ))}
          </div>
        )}
      </section>

      <section>
        <h3 style={{ margin: "0.25rem 0 0.65rem" }}>Backup History</h3>
        {backups.length === 0 ? (
          <EmptyState text="История backup пока не поступала от workflow." />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {backups.slice(0, 10).map((backup) => (
              <Card key={backup.id}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem" }}>
                  <strong>{backup.backup_type}</strong>
                  <span style={{ color: backup.status === "success" ? "var(--era-success)" : "var(--era-error)", fontSize: "var(--era-text-xs)", fontWeight: 800 }}>
                    {statusLabel(backup.status)}
                  </span>
                </div>
                <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
                  {formatDate(backup.completed_at)} · restore: {backup.restore_verified_at ? "проверен" : "нет"}
                </p>
              </Card>
            ))}
          </div>
        )}
      </section>

      <button type="button" onClick={refresh} style={{ alignSelf: "flex-start" }}>Обновить</button>
    </div>
  );
}
