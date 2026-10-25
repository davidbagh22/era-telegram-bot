import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";
import { fetchOperationalEvents } from "../../../api/client";

interface EventsListProps {
  onSelect: (eventId: number) => void;
}

// Events already approved/published — the entry point into per-event
// attendance and points, distinct from the moderation queue above.
export function EventsList({ onSelect }: EventsListProps) {
  const state = useAsync(() => fetchOperationalEvents(), []);

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }
  if (state.status === "error") {
    return <EmptyState text="Не удалось загрузить мероприятия." />;
  }
  if (state.data.length === 0) {
    return <EmptyState text="Действующих мероприятий пока нет." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {state.data.map((event) => (
        <Card key={event.id} style={{ padding: "0.75rem 1rem" }}>
          <button
            type="button"
            onClick={() => onSelect(event.id)}
            style={{ all: "unset", cursor: "pointer", display: "block", width: "100%" }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
              <strong>{event.title}</strong>
              <StatusBadge label={event.status} tone="violet" />
            </div>
            <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
              {event.event_date} · {event.event_time} · {event.location}
            </p>
            <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
              Записано: {event.registered} · Свободно: {event.free} · За визит: +{event.points_for_visit}
            </p>
          </button>
        </Card>
      ))}
    </div>
  );
}
