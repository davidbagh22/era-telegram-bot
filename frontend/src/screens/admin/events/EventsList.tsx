import { useState } from "react";
import { EventDetailsEditor } from "./EventDetailsEditor";
import { setEventPublicListing } from "../../../api/adminEvents";
import { describeActionError, fetchOperationalEvents } from "../../../api/client";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";
import { projectEventStatusLabel } from "../../projects/statusLabels";

interface EventsListProps {
  onSelect: (eventId: number) => void;
  onEditPoster?: (eventId: number) => void;
}

// Events already approved/published — the entry point into per-event
// attendance and points, distinct from the moderation queue above.
export function EventsList({ onSelect, onEditPoster }: EventsListProps) {
  const [editor, setEditor] = useState<number | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [overrides, setOverrides] = useState<Record<number, boolean>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const state = useAsync(() => fetchOperationalEvents(), [refreshVersion]);
  const refresh = () => setRefreshVersion((version) => version + 1);

  const toggleListing = async (eventId: number, currentlyVisible: boolean) => {
    if (busyId !== null) return;
    if (currentlyVisible && !window.confirm("Скрыть мероприятие только из общей афиши? Регистрации, баллы и история сохранятся.")) return;
    setBusyId(eventId);
    setError(null);
    try {
      const updated = await setEventPublicListing(eventId, !currentlyVisible);
      setOverrides((prev) => ({ ...prev, [eventId]: updated.show_in_public_listing }));
    } catch (reason) {
      setError(describeActionError(reason));
    } finally {
      setBusyId(null);
    }
  };

  if (editor !== null) return <EventDetailsEditor eventId={editor} onClose={() => { setEditor(null); refresh(); }} />;

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
      {error && <p role="alert">Не удалось изменить видимость: {error}</p>}
      {state.data.map((event) => (
        <Card key={event.id} style={{ padding: "0.75rem 1rem" }}>
          <button
            type="button"
            onClick={() => onSelect(event.id)}
            style={{ all: "unset", cursor: "pointer", display: "block", width: "100%" }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
              <strong>{event.title}</strong>
              <StatusBadge label={projectEventStatusLabel(event.status)} tone="violet" />
            </div>
            <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
              {event.event_date} · {event.event_time} · {event.location}
            </p>
            <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
              Записано: {event.registered} · Свободно: {event.free} · За визит: +{event.points_for_visit}
            </p>
          </button>
          {onEditPoster && <button onClick={() => setEditor(event.id)}>Редактировать мероприятие</button>}
          {onEditPoster && (
            <>
              <button type="button" onClick={() => onEditPoster(event.id)} style={{ marginTop: ".6rem" }}>
                Изменить афишу
              </button>
              <button type="button" disabled={busyId !== null}
                onClick={() => void toggleListing(event.id, overrides[event.id] ?? (event.show_in_public_listing !== false))}
                style={{ marginTop: ".6rem", marginLeft: ".6rem" }}>
                {(overrides[event.id] ?? (event.show_in_public_listing !== false)) ? "Скрыть из общей афиши" : "Вернуть в общую афишу"}
              </button>
              {(overrides[event.id] ?? (event.show_in_public_listing !== false)) === false &&
                <p role="status" style={{ color: "var(--era-text-muted)" }}>Скрыто из общей афиши; данные участников сохранены.</p>}
            </>
          )}
        </Card>
      ))}
    </div>
  );
}
