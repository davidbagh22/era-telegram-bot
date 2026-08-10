import { useCallback, useState } from "react";
import {
  cancelEventRegistration,
  describeActionError,
  fetchEventActivities,
  fetchEvents,
  registerForEvent,
} from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { PillTabs } from "../../components/PillTabs";
import { StatusBadge } from "../../components/StatusBadge";
import { useAsync } from "../../hooks/useAsync";
import type { EventActivity, EventScope } from "../../types/activity";

const ACTIVITY_STATUS_LABELS: Record<string, string> = {
  pending: "на проверке",
  leader_approved: "проверено лидером",
  approved: "принято",
  rejected: "не принято",
};

// Submitting proof (photo/link/text/file) stays a Bot-only flow — same
// handoff as task submission (see submit_deep_link) — so this panel only
// ever lists activities and status, then hands off to the Bot to submit.
function EventActivitiesPanel({ eventId }: { eventId: number }) {
  const state = useAsync(() => fetchEventActivities(eventId), [eventId]);

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>Загрузка…</p>;
  }
  if (state.status === "error") {
    return <p style={{ color: "var(--era-error)", fontSize: "0.8125rem" }}>Не удалось загрузить активности.</p>;
  }
  if (state.data.length === 0) {
    return <p style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>Дополнительных активностей пока нет.</p>;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      {state.data.map((activity: EventActivity) => (
        <div
          key={activity.id}
          style={{
            border: "1px solid var(--era-border)",
            borderRadius: "0.75rem",
            padding: "0.625rem",
            display: "flex",
            flexDirection: "column",
            gap: "0.25rem",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
            <strong style={{ fontSize: "0.875rem" }}>{activity.title}</strong>
            {activity.my_status && (
              <StatusBadge label={ACTIVITY_STATUS_LABELS[activity.my_status] ?? activity.my_status} tone="violet" />
            )}
          </div>
          <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>{activity.description}</p>
          <p style={{ margin: 0, fontSize: "0.8125rem" }}>+{activity.points} баллов</p>
          {activity.submit_deep_link && (
            <a
              href={activity.submit_deep_link}
              target="_blank"
              rel="noreferrer"
              className="era-btn-primary"
              style={{
                textAlign: "center",
                textDecoration: "none",
                padding: "0.5rem",
                borderRadius: "0.5rem",
                fontSize: "0.8125rem",
              }}
            >
              Отправить результат в боте
            </a>
          )}
        </div>
      ))}
    </div>
  );
}

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
  const [actionError, setActionError] = useState<string | null>(null);
  const [expandedActivitiesId, setExpandedActivitiesId] = useState<number | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleRegister = useCallback(
    async (eventId: number) => {
      setPendingId(eventId);
      setActionError(null);
      try {
        await registerForEvent(eventId);
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setPendingId(null);
      }
    },
    [refresh],
  );

  const handleCancel = useCallback(
    async (eventId: number) => {
      setPendingId(eventId);
      setActionError(null);
      try {
        await cancelEventRegistration(eventId);
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setPendingId(null);
      }
    },
    [refresh],
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <PillTabs options={SCOPES} active={scope} onChange={setScope} />

      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}

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
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                {scope !== "past" &&
                  (isRegistered ? (
                    <button type="button" disabled={pendingId === event.id} onClick={() => handleCancel(event.id)}>
                      Планы изменились
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="era-btn-primary"
                      disabled={pendingId === event.id}
                      onClick={() => handleRegister(event.id)}
                    >
                      Зарегистрироваться
                    </button>
                  ))}
                {isRegistered && (
                  <button
                    type="button"
                    onClick={() =>
                      setExpandedActivitiesId((current) => (current === event.id ? null : event.id))
                    }
                  >
                    {expandedActivitiesId === event.id ? "Скрыть активности" : "✨ Активности"}
                  </button>
                )}
              </div>
              {expandedActivitiesId === event.id && (
                <div style={{ marginTop: "0.625rem" }}>
                  <EventActivitiesPanel eventId={event.id} />
                </div>
              )}
            </Card>
          );
        })}
    </div>
  );
}
