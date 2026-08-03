import { useCallback, useState } from "react";
import { cancelEventRegistration, fetchEvents, registerForEvent } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { PillTabs } from "../../components/PillTabs";
import { StatusBadge } from "../../components/StatusBadge";
import { useAsync } from "../../hooks/useAsync";
import type { EventScope } from "../../types/activity";

const SCOPES: { value: EventScope; label: string }[] = [
  { value: "for_me", label: "Для меня" },
  { value: "all", label: "Все" },
  { value: "mine", label: "Мои" },
  { value: "past", label: "Прошедшие" },
];

const ACTIVE_REGISTRATION_STATUSES = new Set(["registered", "will_come", "attended"]);

export function EventsTab() {
  const [scope, setScope] = useState<EventScope>("for_me");
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchEvents(scope), [scope, refreshKey]);
  const [pendingId, setPendingId] = useState<number | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleRegister = useCallback(
    async (eventId: number) => {
      setPendingId(eventId);
      try {
        await registerForEvent(eventId);
        refresh();
      } finally {
        setPendingId(null);
      }
    },
    [refresh],
  );

  const handleCancel = useCallback(
    async (eventId: number) => {
      setPendingId(eventId);
      try {
        await cancelEventRegistration(eventId);
        refresh();
      } finally {
        setPendingId(null);
      }
    },
    [refresh],
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <PillTabs options={SCOPES} active={scope} onChange={setScope} />

      {state.status === "loading" && (
        <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>
      )}
      {state.status === "error" && <EmptyState text="Не удалось загрузить мероприятия." />}
      {state.status === "ready" && state.data.length === 0 && (
        <EmptyState text="Мероприятий в этом разделе пока нет." />
      )}
      {state.status === "ready" &&
        state.data.map((event) => {
          const isRegistered = ACTIVE_REGISTRATION_STATUSES.has(event.registration_status ?? "");
          return (
            <Card key={event.id}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
                <strong>{event.title}</strong>
                {event.registration_status && (
                  <StatusBadge label={event.registration_status} tone="violet" />
                )}
              </div>
              <p style={{ margin: "0.25rem 0", color: "var(--era-text-muted)" }}>
                {event.event_date} · {event.event_time} · {event.location}
              </p>
              <p style={{ margin: "0 0 0.5rem", color: "var(--era-text-muted)" }}>
                Свободных мест: {event.available_places} · {event.points_for_visit} баллов
              </p>
              {scope !== "past" &&
                (isRegistered ? (
                  <button type="button" disabled={pendingId === event.id} onClick={() => handleCancel(event.id)}>
                    Планы изменились
                  </button>
                ) : (
                  <button type="button" disabled={pendingId === event.id} onClick={() => handleRegister(event.id)}>
                    Зарегистрироваться
                  </button>
                ))}
            </Card>
          );
        })}
    </div>
  );
}
