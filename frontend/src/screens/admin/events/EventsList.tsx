import { useState } from "react";
import { EventDetailsEditor } from "./EventDetailsEditor";
import { cancelAdminEvent, restoreAdminEvent, setEventPublicListing } from "../../../api/adminEvents";
import { describeActionError, fetchOperationalEvents } from "../../../api/client";
import { BottomSheet } from "../../../components/BottomSheet";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";
import { projectEventStatusLabel } from "../../projects/statusLabels";

const RU_MONTHS_GENITIVE = [
  "января",
  "февраля",
  "марта",
  "апреля",
  "мая",
  "июня",
  "июля",
  "августа",
  "сентября",
  "октября",
  "ноября",
  "декабря",
] as const;

function formatEventDateTime(eventDate: string, eventTime?: string | null): string {
  let dateLabel = eventDate;
  const dateMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(eventDate.trim());
  if (dateMatch) {
    const year = Number(dateMatch[1]);
    const monthIndex = Number(dateMatch[2]) - 1;
    const day = Number(dateMatch[3]);
    const monthName = RU_MONTHS_GENITIVE[monthIndex];
    if (monthName && day >= 1 && day <= 31) {
      const currentYear = new Date().getFullYear();
      dateLabel = year !== currentYear ? `${day} ${monthName} ${year}` : `${day} ${monthName}`;
    }
  }
  const rawTime = (eventTime ?? "").trim();
  const timeMatch = /^(\d{2}:\d{2})(?::\d{2})?/.exec(rawTime);
  const timeLabel = timeMatch ? timeMatch[1] : rawTime;
  return timeLabel ? `${dateLabel}, ${timeLabel}` : dateLabel;
}

interface EventsListProps {
  onSelect: (eventId: number) => void;
  onEditPoster?: (eventId: number) => void;
  onOpenParticipants?: (eventId: number) => void;
  canRemove?: boolean;
}

interface PendingRemoveEvent {
  id: number;
  title: string;
  registered: number;
  status: string;
}

// Events already approved/published — the entry point into per-event
// attendance and points, distinct from the moderation queue above.
export function EventsList({ onSelect, onEditPoster, onOpenParticipants, canRemove = false }: EventsListProps) {
  const [editor, setEditor] = useState<number | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [overrides, setOverrides] = useState<Record<number, boolean>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<PendingRemoveEvent | null>(null);
  const [undoEvent, setUndoEvent] = useState<{ id: number; title: string } | null>(null);
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

  const handleConfirmRemove = async () => {
    if (!confirmRemove || busyId !== null) return;
    const target = confirmRemove;
    setBusyId(target.id);
    setError(null);
    try {
      await cancelAdminEvent(target.id);
      setConfirmRemove(null);
      setUndoEvent({ id: target.id, title: target.title });
      refresh();
    } catch (reason) {
      setError(describeActionError(reason));
      setConfirmRemove(null);
    } finally {
      setBusyId(null);
    }
  };

  const handleUndoRemove = async () => {
    if (!undoEvent || busyId !== null) return;
    const target = undoEvent;
    setBusyId(target.id);
    setError(null);
    try {
      await restoreAdminEvent(target.id);
      setUndoEvent(null);
      refresh();
    } catch (reason) {
      setError(describeActionError(reason));
    } finally {
      setBusyId(null);
    }
  };

  if (editor !== null) return <EventDetailsEditor eventId={editor} onClose={() => { setEditor(null); refresh(); }} />;

  const undoBanner = undoEvent && (
    <div data-testid="event-remove-undo-banner">
      <Card
        style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", padding: "0.75rem 0.9rem" }}
      >
        <div style={{ minWidth: 0 }}>
          <strong style={{ display: "block", fontSize: "0.875rem" }}>Мероприятие убрано</strong>
          <span style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem", overflowWrap: "anywhere" }}>
            {undoEvent.title} · записано в аудит
          </span>
        </div>
        <button
          type="button"
          disabled={busyId === undoEvent.id}
          onClick={() => void handleUndoRemove()}
          style={{ flexShrink: 0 }}
        >
          {busyId === undoEvent.id ? "Возвращаем…" : "Вернуть"}
        </button>
      </Card>
    </div>
  );

  const confirmSheet = (
    <BottomSheet
      open={confirmRemove !== null}
      onClose={() => {
        if (busyId === null) setConfirmRemove(null);
      }}
      title="Убрать мероприятие?"
    >
      {confirmRemove && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <strong style={{ fontSize: "0.95rem", overflowWrap: "anywhere" }}>{confirmRemove.title}</strong>
          <p data-testid="event-remove-registrations-note" style={{ margin: 0, fontSize: "0.875rem", fontWeight: 600 }}>
            {confirmRemove.registered > 0
              ? confirmRemove.status === "completed" || confirmRemove.status === "report_submitted"
                ? `Зарегистрировано участников: ${confirmRemove.registered}. Мероприятие уже завершено, повторное уведомление об отмене не отправится.`
                : `Зарегистрировано участников: ${confirmRemove.registered}. Им придёт уведомление «Мероприятие отменено».`
              : "Регистраций пока нет."}
          </p>
          <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.85rem" }}>
            Мероприятие исчезнет из списка и общей афиши. Баллы, посещаемость и сертификаты сохранятся.
            Действие запишется в журнал аудита — его можно сразу отменить кнопкой «Вернуть».
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.5rem" }}>
            <button
              type="button"
              disabled={busyId === confirmRemove.id}
              onClick={() => setConfirmRemove(null)}
            >
              Отмена
            </button>
            <button
              type="button"
              className="era-btn-primary"
              disabled={busyId === confirmRemove.id}
              onClick={() => void handleConfirmRemove()}
            >
              {busyId === confirmRemove.id ? "Убираем…" : "Убрать мероприятие"}
            </button>
          </div>
        </div>
      )}
    </BottomSheet>
  );

  if (state.status === "loading") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {error && <p role="alert" style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{error}</p>}
        {undoBanner}
        <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>
        {confirmSheet}
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: "0.75rem" }}>
        {error && <p role="alert" style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{error}</p>}
        {undoBanner}
        <EmptyState text="Не удалось загрузить мероприятия." />
        <button type="button" onClick={refresh}>Повторить загрузку</button>
        {confirmSheet}
      </div>
    );
  }
  if (state.data.length === 0) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {error && <p role="alert" style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{error}</p>}
        {undoBanner}
        <EmptyState text="Действующих мероприятий пока нет." />
        <button type="button" onClick={refresh} style={{ alignSelf: "flex-start" }}>Обновить список</button>
        {confirmSheet}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" onClick={refresh} style={{ alignSelf: "flex-start" }}>Обновить список</button>
      {error && <p role="alert" style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{error}</p>}
      {undoBanner}
      {state.data.map((event) => {
        const isListed = overrides[event.id] ?? (event.show_in_public_listing !== false);
        const dateTimeLabel = formatEventDateTime(event.event_date, event.event_time);
        return (
          <Card key={event.id} style={{ padding: "0.875rem 1rem" }}>
            <button
              type="button"
              onClick={() => onSelect(event.id)}
              style={{ all: "unset", cursor: "pointer", display: "block", width: "100%" }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "0.5rem",
                  flexWrap: "wrap",
                  marginBottom: "0.4rem",
                }}
              >
                <StatusBadge label={projectEventStatusLabel(event.status)} tone="violet" />
                <span style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem", whiteSpace: "nowrap" }}>
                  {dateTimeLabel}
                </span>
              </div>
              <strong style={{ display: "block", fontSize: "1rem", lineHeight: 1.3, overflowWrap: "anywhere" }}>
                {event.title}
              </strong>
              {event.location && (
                <p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem", overflowWrap: "anywhere" }}>
                  {event.location}
                </p>
              )}
              <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
                Записано: {event.registered} · Свободно: {event.free} · За визит: +{event.points_for_visit}
              </p>
            </button>
            {(onOpenParticipants || onEditPoster || canRemove) && (
              <div
                data-testid={`event-actions-${event.id}`}
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                  gap: "0.5rem",
                  marginTop: "0.75rem",
                }}
              >
                {onOpenParticipants && (
                  <button
                    type="button"
                    className="era-btn-primary"
                    onClick={() => onOpenParticipants(event.id)}
                    style={{ gridColumn: "1 / -1", width: "100%", minHeight: "2.625rem" }}
                  >
                    Участники · {event.registered}
                  </button>
                )}
                {onEditPoster && (
                  <>
                    <button
                      type="button"
                      onClick={() => setEditor(event.id)}
                      style={{ width: "100%", minHeight: "2.625rem", padding: "0.5rem 0.625rem", fontSize: "0.8125rem" }}
                    >
                      Редактировать мероприятие
                    </button>
                    <button
                      type="button"
                      onClick={() => onEditPoster(event.id)}
                      style={{ width: "100%", minHeight: "2.625rem", padding: "0.5rem 0.625rem", fontSize: "0.8125rem" }}
                    >
                      Изменить афишу
                    </button>
                    <button
                      type="button"
                      disabled={busyId !== null}
                      onClick={() => void toggleListing(event.id, isListed)}
                      style={{ gridColumn: "1 / -1", width: "100%", minHeight: "2.625rem", padding: "0.5rem 0.75rem", fontSize: "0.8125rem" }}
                    >
                      {isListed ? "Скрыть из общей афиши" : "Вернуть в общую афишу"}
                    </button>
                  </>
                )}
                {canRemove && (
                  <button
                    type="button"
                    data-testid={`event-remove-${event.id}`}
                    disabled={busyId !== null}
                    onClick={() => {
                      setError(null);
                      setConfirmRemove({
                        id: event.id,
                        title: event.title,
                        registered: event.registered,
                        status: event.status,
                      });
                    }}
                    style={{
                      gridColumn: "1 / -1",
                      width: "100%",
                      minHeight: "2.625rem",
                      padding: "0.5rem 0.75rem",
                      fontSize: "0.8125rem",
                      color: "var(--era-error, var(--era-red))",
                      borderColor: "var(--era-error, var(--era-red))",
                    }}
                  >
                    Убрать
                  </button>
                )}
              </div>
            )}
            {onEditPoster && !isListed && (
              <p role="status" style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
                Скрыто из общей афиши; данные участников сохранены.
              </p>
            )}
          </Card>
        );
      })}
      {confirmSheet}
    </div>
  );
}
