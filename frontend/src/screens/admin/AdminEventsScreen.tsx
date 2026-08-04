import { useCallback, useState } from "react";
import { decideEvent, fetchAdminEvents } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { useAsync } from "../../hooks/useAsync";
import type { EventDecisionAction } from "../../types/admin";

const DECISIONS: { action: EventDecisionAction; label: string; primary?: boolean }[] = [
  { action: "approve", label: "Одобрить", primary: true },
  { action: "revise", label: "На доработку" },
  { action: "reject", label: "Отклонить" },
];

export function AdminEventsScreen() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAdminEvents(), [refreshKey]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [comments, setComments] = useState<Record<number, string>>({});

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleDecide = useCallback(
    async (eventId: number, action: EventDecisionAction) => {
      const comment = (comments[eventId] ?? "").trim();
      if (action !== "approve" && !comment) return;
      setBusyId(eventId);
      try {
        await decideEvent(eventId, action, comment);
        refresh();
      } finally {
        setBusyId(null);
      }
    },
    [comments, refresh],
  );

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }
  if (state.status === "error") {
    return <EmptyState text="Не удалось загрузить мероприятия." />;
  }
  if (state.data.length === 0) {
    return <EmptyState text="Мероприятий на рассмотрении нет." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {state.data.map((event) => (
        <Card key={event.id}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <strong>{event.title}</strong>
            <StatusBadge label={event.status} tone="violet" />
          </div>
          <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>
            {event.event_date} · {event.event_time} · {event.location}
          </p>
          <p style={{ margin: "0 0 0.5rem", color: "var(--era-text-muted)" }}>{event.description}</p>
          <textarea
            placeholder="Комментарий автору (обязателен для доработки/отклонения)"
            value={comments[event.id] ?? ""}
            onChange={(input) =>
              setComments((previous) => ({ ...previous, [event.id]: input.target.value }))
            }
            rows={2}
            style={{
              width: "100%",
              fontFamily: "var(--era-font-body)",
              padding: "0.5rem",
              borderRadius: "0.5rem",
              border: "1px solid var(--era-border)",
              background: "var(--era-bg)",
              color: "var(--era-text)",
              marginBottom: "0.5rem",
            }}
          />
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            {DECISIONS.map(({ action, label, primary }) => (
              <button
                key={action}
                type="button"
                className={primary ? "era-btn-primary" : undefined}
                disabled={busyId === event.id}
                onClick={() => handleDecide(event.id, action)}
              >
                {label}
              </button>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}
