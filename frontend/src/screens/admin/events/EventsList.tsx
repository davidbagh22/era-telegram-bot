import { useState } from "react";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";
import { fetchOperationalEvents } from "../../../api/client";

interface EventsListProps {
  onSelect: (eventId: number) => void;
  onEditPoster?: (eventId: number) => void;
}

// Events already approved/published — the entry point into per-event
// attendance and points, distinct from the moderation queue above.
export function EventsList({ onSelect, onEditPoster }: EventsListProps) {
  const [refreshVersion, setRefreshVersion] = useState(0);
  const state = useAsync(() => fetchOperationalEvents(), [refreshVersion]);
  const refresh = () => setRefreshVersion((version) => version + 1);

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }
  if (state.status === "error") {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: "0.75rem" }}>
        <EmptyState text="Не удалось загрузить мероприятия." />
        <button type="button" onClick={refresh}>Повторить загрузку</button>
      </div>
    );
  }
  if (state.data.length === 0) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: "0.75rem" }}>
        <EmptyState text="Действующих мероприятий пока нет." />
        <button type="button" onClick={refresh}>Обновить список</button>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" onClick={refresh} style={{ alignSelf: "flex-start" }}>Обновить список</button>
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
          {onEditPoster && (
            <button type="button" onClick={() => onEditPoster(event.id)} style={{ marginTop: ".6rem" }}>
              Изменить афишу
            </button>
          )}
        </Card>
      ))}
    </div>
  );
}
