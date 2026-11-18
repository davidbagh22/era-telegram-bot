import { useMemo, useState } from "react";
import { fetchEvents } from "../../api/client";
import { MediaRequestButton } from "../../components/MediaRequestButton";
import { EmptyState } from "../../components/EmptyState";
import { useAsync } from "../../hooks/useAsync";
import type { EventItem } from "../../types/activity";

const PAST_STATUSES = new Set(["completed", "cancelled", "archived", "rejected"]);

function isMediaCandidate(event: EventItem, today: string): boolean {
  if (PAST_STATUSES.has(event.status) || PAST_STATUSES.has(event.display_status)) {
    return false;
  }
  // event_date is YYYY-MM-DD — keep today and future for media briefs.
  return Boolean(event.event_date) && event.event_date >= today;
}

/** Compact media-request flow for Mode лидера: pick an upcoming event → package + due date. */
export function LeaderMediaRequestPanel({ onBack }: { onBack: () => void }) {
  const eventsState = useAsync(() => fetchEvents("all"), []);
  const [eventId, setEventId] = useState<number | null>(null);

  const events = useMemo(() => {
    if (eventsState.status !== "ready") return [];
    const today = new Date().toISOString().slice(0, 10);
    return eventsState.data
      .filter((item) => isMediaCandidate(item, today))
      .slice(0, 12);
  }, [eventsState]);

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
        <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)", lineHeight: 1.45 }}>
          1) Выберите ближайшее событие. 2) Пакет и срок. 3) Отправьте команде Медиа — это заказ материала, не пост в канал.
        </p>
      </div>

      {eventsState.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загружаем события…</p>}
      {eventsState.status === "error" && <EmptyState text="Не удалось загрузить события." />}
      {eventsState.status === "ready" && events.length === 0 && (
        <EmptyState text="Нет ближайших событий для медиа-запроса." />
      )}

      {events.length > 0 && (
        <label style={{ display: "grid", gap: "0.35rem" }}>
          <span style={{ fontSize: "0.78rem", color: "var(--era-text-muted)", fontWeight: 700 }}>1. Событие</span>
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
                {item.event_date} · {item.title}
              </option>
            ))}
          </select>
        </label>
      )}

      {eventId ? (
        <MediaRequestButton key={eventId} sourceType="event" sourceId={eventId} defaultOpen />
      ) : events.length > 0 ? (
        <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.84rem", lineHeight: 1.45 }}>
          После выбора события откроется заказ: пакет → срок → отправить.
        </p>
      ) : null}
    </div>
  );
}
