import { useMemo, useState } from "react";
import { fetchEvents } from "../../api/client";
import { MediaRequestButton } from "../../components/MediaRequestButton";
import { EmptyState } from "../../components/EmptyState";
import { useAsync } from "../../hooks/useAsync";

/** Compact media-request flow for Mode лидера: pick an upcoming event → package + due date. */
export function LeaderMediaRequestPanel({ onBack }: { onBack: () => void }) {
  const eventsState = useAsync(() => fetchEvents("upcoming"), []);
  const [eventId, setEventId] = useState<number | null>(null);

  const events = useMemo(
    () => (eventsState.status === "ready" ? eventsState.data.slice(0, 12) : []),
    [eventsState],
  );

  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>
        ← Назад
      </button>
      <div>
        <p style={{ margin: "0 0 0.25rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
          Режим лидера
        </p>
        <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "var(--era-text-2xl)", margin: 0 }}>
          Медиа-запрос
        </h1>
        <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)" }}>
          Выбери событие, пакет (фото / рилс / полный) и срок для редакции.
        </p>
      </div>

      {eventsState.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загружаем события…</p>}
      {eventsState.status === "error" && <EmptyState text="Не удалось загрузить события." />}
      {eventsState.status === "ready" && events.length === 0 && (
        <EmptyState text="Нет ближайших событий для медиа-запроса." />
      )}

      {events.length > 0 && (
        <label style={{ display: "grid", gap: "0.35rem" }}>
          <span style={{ fontSize: "0.78rem", color: "var(--era-text-muted)", fontWeight: 700 }}>Событие</span>
          <select
            value={eventId ?? ""}
            onChange={(event) => setEventId(event.target.value ? Number(event.target.value) : null)}
            style={{
              minHeight: "2.75rem",
              borderRadius: "0.75rem",
              border: "1px solid var(--era-border)",
              background: "var(--era-surface)",
              color: "var(--era-text)",
              padding: "0.5rem 0.65rem",
              fontFamily: "var(--era-font-body)",
            }}
          >
            <option value="">Выберите событие</option>
            {events.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
        </label>
      )}

      {eventId ? <MediaRequestButton sourceType="event" sourceId={eventId} /> : null}
    </div>
  );
}
