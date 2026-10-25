import { fetchCalendar } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { useAsync } from "../../hooks/useAsync";

export function CalendarTab() {
  const state = useAsync(() => fetchCalendar(), []);

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }
  if (state.status === "error") {
    return <EmptyState text="Не удалось загрузить календарь." />;
  }
  if (state.data.length === 0) {
    return <EmptyState text="В ближайшие два месяца пока ничего не запланировано." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {state.data.map((item) => (
        <Card key={`${item.kind}-${item.id}`}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <strong>{item.title}</strong>
            <span style={{ color: "var(--era-text-muted)", fontSize: "0.75rem" }}>
              {item.kind === "event" ? "Мероприятие" : "Задача"}
            </span>
          </div>
          <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
            {item.date}
            {item.time ? ` · ${item.time}` : ""}
          </p>
        </Card>
      ))}
    </div>
  );
}
