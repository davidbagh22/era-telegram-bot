import { fetchHistory } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { useAsync } from "../../hooks/useAsync";

const KIND_LABELS: Record<string, string> = {
  event_attended: "Мероприятие",
  task_completed: "Задача",
  portfolio: "Портфолио",
  points: "Баллы",
};

export function HistoryTab() {
  const state = useAsync(() => fetchHistory(), []);

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }
  if (state.status === "error") {
    return <EmptyState text="Не удалось загрузить историю." />;
  }
  if (state.data.length === 0) {
    return <EmptyState text="История пока пуста." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {state.data.map((entry, index) => (
        <Card key={index}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <strong>{entry.title}</strong>
            <span style={{ color: "var(--era-text-muted)", fontSize: "0.75rem" }}>
              {KIND_LABELS[entry.kind] ?? entry.kind}
            </span>
          </div>
          <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
            {entry.date} · {entry.detail}
          </p>
        </Card>
      ))}
    </div>
  );
}
