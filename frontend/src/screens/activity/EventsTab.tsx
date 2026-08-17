import { useCallback, useEffect, useMemo, useState } from "react";
import {
  cancelEventRegistration,
  describeActionError,
  fetchEventActivities,
  fetchEvents,
  registerForEvent,
} from "../../api/client";
import { BottomSheet } from "../../components/BottomSheet";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import { StatusBadge } from "../../components/StatusBadge";
import { useToast } from "../../components/Toast";
import { useAsync } from "../../hooks/useAsync";
import { successHaptic } from "../../telegram/webApp";
import type { EventActivity, EventItem, EventScope } from "../../types/activity";
import { EventAttendancePanel } from "./EventAttendancePanel";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

const ACTIVITY_STATUS_LABELS: Record<string, string> = {
  pending: "На проверке",
  leader_approved: "Проверено лидером",
  approved: "Принято",
  rejected: "Нужно исправить",
};

const ACTIVE_REGISTRATION_STATUSES = new Set(["registered", "will_come", "attended"]);
const WAITLIST_STATUS = "waitlist";

const SCOPES: { value: EventScope; label: string; description: string }[] = [
  { value: "for_me", label: "Для меня", description: "Ближайшие события и то, где вы уже участвуете" },
  { value: "all", label: "Все события", description: "Вся открытая афиша ЭРА" },
  { value: "mine", label: "Мои регистрации", description: "События, на которые вы записаны" },
  { value: "past", label: "Прошедшие", description: "История мероприятий" },
];

function formatDate(value: string): string {
  const date = new Date(`${value}T00:00:00`);
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", weekday: "short" }).format(date);
}

function capacityText(event: EventItem): string {
  if (event.participant_limit === null) return "Без ограничения мест";
  return `${event.registered_count} / ${event.participant_limit} участников`;
}

function posterSrc(event: EventItem): string | null {
  if (!event.poster_url) return null;
  return `${API_BASE_URL}/api/v1/event-posters/${event.id}`;
}

function addToCalendar(event: EventItem): void {
  const pad = (value: string) => value.replace(/[-:]/g, "");
  const start = `${pad(event.event_date)}T${pad(event.event_time)}00`;
  const endTime = event.end_time ?? event.event_time;
  const end = `${pad(event.event_date)}T${pad(endTime)}00`;
  const description = (event.full_description ?? event.description).replace(/\n/g, "\\n");
  const location = [event.location, event.address].filter(Boolean).join(", ");
  const ics = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//ERA//Events//RU",
    "BEGIN:VEVENT",
    `UID:era-event-${event.id}`,
    `DTSTART:${start}`,
    `DTEND:${end}`,
    `SUMMARY:${event.title}`,
    `DESCRIPTION:${description}`,
    `LOCATION:${location}`,
    "END:VEVENT",
    "END:VCALENDAR",
  ].join("\r\n");
  const blob = new Blob([ics], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `ERA-${event.id}.ics`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 500);
}

function EventActivitiesPanel({ eventId }: { eventId: number }) {
  const state = useAsync(() => fetchEventActivities(eventId), [eventId]);

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>Загружаем задания…</p>;
  }
  if (state.status === "error") {
    return <p style={{ color: "var(--era-error)", fontSize: "0.8125rem" }}>Не удалось загрузить задания мероприятия.</p>;
  }
  if (state.data.length === 0) {
    return <p style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>Дополнительных заданий пока нет.</p>;
  }

  return (
    <div className="era-stagger" style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
      {state.data.map((activity: EventActivity) => (
        <div
          key={activity.id}
          style={{
            border: "1px solid var(--era-border)",
            background: "var(--era-surface-2)",
            borderRadius: "0.9rem",
            padding: "0.8rem",
            display: "flex",
            flexDirection: "column",
            gap: "0.35rem",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", alignItems: "flex-start" }}>
            <strong>{activity.title}</strong>
            {activity.my_status && <StatusBadge label={ACTIVITY_STATUS_LABELS[activity.my_status] ?? "В работе"} tone="violet" />}
          </div>
          <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.85rem" }}>{activity.description}</p>
          <strong style={{ fontSize: "0.82rem" }}>+{activity.points} баллов</strong>
          {activity.submit_deep_link && (
            <a
              href={activity.submit_deep_link}
              target="_blank"
              rel="noreferrer"
              className="era-btn-primary"
              style={{ textAlign: "center", textDecoration: "none", marginTop: "0.35rem", minHeight: 44, display: "grid", placeItems: "center", borderRadius: "var(--era-radius-control)" }}
            >
              Отправить результат
            </a>
          )}
        </div>
      ))}
    </div>
  );
}

function EventPoster({ event, compact = false }: { event: EventItem; compact?: boolean }) {
  const src = posterSrc(event);
  const height = compact ? 150 : 245;
  if (src) {
    return (
      <img
        src={src}
        alt={`Афиша ${event.title}`}
        style={{ width: "100%", height, objectFit: "cover", borderRadius: compact ? "1rem" : "1.25rem", display: "block" }}
      />
    );
  }
  return (
    <div
      aria-hidden="true"
      style={{
        height,
        borderRadius: compact ? "1rem" : "1.25rem",
        background: "radial-gradient(circle at 80% 20%, rgba(255,255,255,.16), transparent 32%), var(--era-gradient-signal)",
        display: "flex",
        alignItems: "flex-end",
        padding: compact ? "1rem" : "1.25rem",
        boxSizing: "border-box",
        overflow: "hidden",
        border: "1px solid rgba(255,255,255,.14)",
      }}
    >
      <span style={{ fontSize: compact ? "2rem" : "3rem", fontWeight: 900, opacity: 0.95, color: "#fff" }}>ЭРА</span>
    </div>
  );
}

interface EventDetailProps {
  event: EventItem;
  pending: boolean;
  actionError: string | null;
  onRegister: () => void;
  onCancelRequest: () => void;
  onBack: () => void;
}

function EventDetail({ event, pending, actionError, onRegister, onCancelRequest, onBack }: EventDetailProps) {
  const registered = ACTIVE_REGISTRATION_STATUSES.has(event.registration_status ?? "");
  const waitlisted = event.registration_status === WAITLIST_STATUS;

  return (
    <div className="era-page" style={{ display: "flex", flexDirection: "column", gap: "0.85rem", paddingBottom: "7.2rem" }}>
      <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← К событиям</button>
      <EventPoster event={event} />

      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <StatusBadge label={event.display_status} tone={registered ? "violet" : "neutral"} />
        <h2 style={{ fontSize: "clamp(1.65rem, 7vw, 2.35rem)", lineHeight: 1.05, margin: 0 }}>{event.title}</h2>
        {event.short_description && <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "1rem", lineHeight: 1.45 }}>{event.short_description}</p>}
      </div>

      <Card style={{ padding: "0.95rem" }}>
        <div style={{ display: "grid", gap: "0.75rem" }}>
          <div><span style={{ color: "var(--era-text-muted)", fontSize: "0.78rem" }}>КОГДА</span><div style={{ fontWeight: 800, marginTop: 2 }}>{formatDate(event.event_date)} · {event.event_time}{event.end_time ? `–${event.end_time}` : ""}</div></div>
          <div><span style={{ color: "var(--era-text-muted)", fontSize: "0.78rem" }}>ГДЕ</span><div style={{ fontWeight: 800, marginTop: 2 }}>{event.location}</div>{event.address && <div style={{ color: "var(--era-text-muted)", fontSize: "0.85rem" }}>{event.address}</div>}</div>
          {event.organizer && <div><span style={{ color: "var(--era-text-muted)", fontSize: "0.78rem" }}>ОРГАНИЗАТОР</span><div style={{ fontWeight: 800, marginTop: 2 }}>{event.organizer}</div></div>}
        </div>
      </Card>

      <Card>
        <strong style={{ fontSize: "1.05rem" }}>О событии</strong>
        <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.55, margin: "0.55rem 0 0", color: "var(--era-text-muted)" }}>{event.full_description ?? event.description}</p>
      </Card>

      {event.participant_value && (
        <Card style={{ background: "linear-gradient(145deg, rgba(99,44,255,.12), rgba(255,100,0,.06))" }}>
          <strong>Что вы получите</strong>
          <p style={{ whiteSpace: "pre-wrap", margin: "0.45rem 0 0", lineHeight: 1.5 }}>{event.participant_value}</p>
        </Card>
      )}

      {event.program.length > 0 && (
        <section>
          <h3 style={{ margin: "0 0 0.6rem" }}>Программа</h3>
          <div className="era-stagger" style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {event.program.map((item, index) => (
              <Card key={`${item.title ?? "activity"}-${index}`} style={{ padding: "0.8rem 0.9rem" }}>
                <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
                  {item.time && <strong style={{ minWidth: 48 }}>{item.time}</strong>}
                  <div>
                    <strong>{item.title || `Активность ${index + 1}`}</strong>
                    {item.description && <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "0.86rem" }}>{item.description}</p>}
                    {item.responsible && <p style={{ margin: "0.25rem 0 0", fontSize: "0.8rem" }}>Ведёт: {item.responsible}</p>}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </section>
      )}

      {event.participant_tasks.length > 0 && (
        <section>
          <h3 style={{ margin: "0 0 0.6rem" }}>Задания и баллы</h3>
          <div className="era-stagger" style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {event.participant_tasks.map((task, index) => (
              <Card key={`${task.title ?? "task"}-${index}`} style={{ padding: "0.8rem 0.9rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem" }}>
                  <strong>{task.title || `Задание ${index + 1}`}</strong>
                  {typeof task.points === "number" && <strong style={{ whiteSpace: "nowrap", color: "var(--era-gold-ink)" }}>+{task.points}</strong>}
                </div>
                {task.description && <p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)", fontSize: "0.86rem" }}>{task.description}</p>}
              </Card>
            ))}
          </div>
        </section>
      )}

      <Card>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.7rem" }}>
          <div><span style={{ color: "var(--era-text-muted)", fontSize: "0.78rem" }}>УЧАСТНИКИ</span><div style={{ fontSize: "1.25rem", fontWeight: 900 }}>{capacityText(event)}</div>{event.remaining_count !== null && <div style={{ color: "var(--era-text-muted)", fontSize: "0.82rem" }}>Осталось {event.remaining_count}</div>}</div>
          <div><span style={{ color: "var(--era-text-muted)", fontSize: "0.78rem" }}>ЗА ПОСЕЩЕНИЕ</span><div style={{ fontSize: "1.25rem", fontWeight: 900 }}>{event.points_for_visit > 0 ? `+${event.points_for_visit}` : "—"}</div><div style={{ color: "var(--era-text-muted)", fontSize: "0.82rem" }}>баллов</div></div>
        </div>
      </Card>

      {(registered || waitlisted) && (
        <Card style={registered ? { borderColor: "rgba(85,189,130,.18)" } : undefined}>
          <strong>{waitlisted ? "Вы в листе ожидания" : "✓ Вы участвуете"}</strong>
          <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "0.86rem" }}>
            {waitlisted ? "Если место освободится, бот сообщит вам автоматически." : "Подробности и напоминания придут в бот. Если планы изменятся — освободите место заранее."}
          </p>
          {registered && <div style={{ marginTop: "0.75rem" }}><EventActivitiesPanel eventId={event.id} /></div>}
        </Card>
      )}

      {registered && <EventAttendancePanel eventId={event.id} />}

      {event.project_id && <button type="button" onClick={() => { window.location.hash = `#/projects/${event.project_id}`; }}>Открыть связанный проект →</button>}
      <button type="button" onClick={() => addToCalendar(event)}>Добавить в календарь</button>
      {event.chat_url && <a href={event.chat_url} target="_blank" rel="noreferrer" className="era-btn-secondary" style={{ textAlign: "center", textDecoration: "none" }}>Открыть чат</a>}
      {event.contact && <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.86rem" }}>Связь: {event.contact}</p>}
      {actionError && <p style={{ color: "var(--era-error)", margin: 0 }}>{actionError}</p>}

      <div
        style={{
          position: "fixed",
          left: "max(1rem, env(safe-area-inset-left))",
          right: "max(1rem, env(safe-area-inset-right))",
          bottom: "calc(5.4rem + env(safe-area-inset-bottom))",
          zIndex: 20,
          padding: "0.55rem",
          border: "1px solid var(--era-nav-border, var(--era-border))",
          borderRadius: "1.25rem",
          background: "var(--era-nav-glass, var(--era-glass))",
          backdropFilter: "blur(20px) saturate(140%)",
          WebkitBackdropFilter: "blur(20px) saturate(140%)",
          boxShadow: "var(--era-shadow-dock)",
        }}
      >
        {registered ? (
          <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: ".5rem" }}>
            <div
              className="era-success-state"
              style={{ minHeight: 44, borderRadius: "var(--era-radius-control)", display: "grid", placeItems: "center", background: "var(--era-success-bg)", color: "var(--era-success)", fontWeight: 850 }}
            >
              ✓ Вы участвуете
            </div>
            <button type="button" disabled={pending} onClick={onCancelRequest} style={{ minWidth: 106 }}>
              {pending ? "…" : "Отказаться"}
            </button>
          </div>
        ) : waitlisted ? (
          <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: ".5rem" }}>
            <div style={{ minHeight: 44, borderRadius: "var(--era-radius-control)", display: "grid", placeItems: "center", background: "var(--era-tint-gold)", color: "var(--era-gold-ink)", fontWeight: 850 }}>
              В листе ожидания
            </div>
            <button type="button" disabled={pending} onClick={onCancelRequest} style={{ minWidth: 106 }}>Отказаться</button>
          </div>
        ) : event.can_register ? (
          <button type="button" className="era-btn-primary" disabled={pending} onClick={onRegister} style={{ width: "100%" }}>
            {pending ? "● Сохраняем…" : event.remaining_count === 0 && event.waitlist_enabled ? "Встать в лист ожидания" : "Участвовать"}
          </button>
        ) : (
          <button type="button" disabled style={{ width: "100%" }}>Регистрация недоступна</button>
        )}
      </div>
    </div>
  );
}

interface EventsTabProps {
  initialItemId?: number | null;
}

export function EventsTab({ initialItemId }: EventsTabProps = {}) {
  const [scope, setScope] = useState<EventScope>(initialItemId ? "all" : "for_me");
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchEvents(scope), [scope, refreshKey]);
  const [selectedId, setSelectedId] = useState<number | null>(initialItemId ?? null);
  const [selectedOverride, setSelectedOverride] = useState<EventItem | null>(null);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [cancelTarget, setCancelTarget] = useState<EventItem | null>(null);
  const [registrationSuccess, setRegistrationSuccess] = useState<EventItem | null>(null);
  const [filterOpen, setFilterOpen] = useState(false);
  const [deepLinkFallbackTried, setDeepLinkFallbackTried] = useState(false);
  const toast = useToast();

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  useEffect(() => {
    if (initialItemId) {
      setSelectedId(initialItemId);
      setScope("all");
      setDeepLinkFallbackTried(false);
    }
  }, [initialItemId]);

  useEffect(() => {
    if (!initialItemId || state.status !== "ready" || selectedId !== initialItemId) return;
    const found = state.data.some((item) => item.id === initialItemId);
    if (!found && scope === "all" && !deepLinkFallbackTried) {
      setDeepLinkFallbackTried(true);
      setScope("past");
    }
  }, [deepLinkFallbackTried, initialItemId, scope, selectedId, state]);

  const selected = useMemo(() => {
    if (selectedOverride?.id === selectedId) return selectedOverride;
    if (state.status !== "ready" || selectedId === null) return null;
    return state.data.find((item) => item.id === selectedId) ?? null;
  }, [selectedId, selectedOverride, state]);

  const handleRegister = useCallback(async (eventId: number) => {
    setPendingId(eventId);
    setActionError(null);
    try {
      const result = await registerForEvent(eventId);
      setSelectedOverride(result);
      refresh();
      if (result.registration_status === WAITLIST_STATUS) {
        toast.show("Вы в листе ожидания", "success");
      } else {
        successHaptic();
        setRegistrationSuccess(result);
        toast.show("Место за вами", "success");
      }
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setPendingId(null);
    }
  }, [refresh, toast]);

  const handleCancel = useCallback(async (eventId: number) => {
    setPendingId(eventId);
    setActionError(null);
    try {
      const result = await cancelEventRegistration(eventId);
      setSelectedOverride(result);
      refresh();
      toast.show("Участие отменено", "info");
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setPendingId(null);
      setCancelTarget(null);
    }
  }, [refresh, toast]);

  const openEvent = (id: number) => {
    setSelectedId(id);
    setSelectedOverride(null);
    setActionError(null);
    setRegistrationSuccess(null);
    window.location.hash = `#/events/${id}`;
  };

  const closeEvent = () => {
    setSelectedId(null);
    setSelectedOverride(null);
    setActionError(null);
    setRegistrationSuccess(null);
    setScope("for_me");
    window.location.hash = "#/events";
  };

  if (selectedId !== null) {
    if (state.status === "loading") return <SkeletonList count={3} />;
    if (state.status === "error") return <EmptyState text="Не удалось открыть мероприятие. Проверьте соединение и попробуйте снова." />;
    if (!selected && (scope !== "all" || deepLinkFallbackTried)) {
      return (
        <div className="era-page" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <button type="button" onClick={closeEvent} style={{ alignSelf: "flex-start" }}>← К событиям</button>
          <Card>
            <h2 style={{ marginTop: 0 }}>Этот объект больше недоступен</h2>
            <p style={{ marginBottom: 0, color: "var(--era-text-muted)" }}>Мероприятие удалено, закрыто для просмотра или ссылка больше неактуальна.</p>
          </Card>
        </div>
      );
    }
    if (selected) {
      return (
        <>
          <EventDetail
            event={selected}
            pending={pendingId === selected.id}
            actionError={actionError}
            onRegister={() => void handleRegister(selected.id)}
            onCancelRequest={() => setCancelTarget(selected)}
            onBack={closeEvent}
          />

          <BottomSheet open={cancelTarget !== null} onClose={() => setCancelTarget(null)} title="Отказаться от участия?">
            <p style={{ color: "var(--era-text-muted)", margin: "0 0 1rem" }}>Место освободится для другого участника. Вернуться можно будет только если регистрация всё ещё открыта.</p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
              <button type="button" onClick={() => setCancelTarget(null)}>Остаться</button>
              <button type="button" className="era-btn-primary" disabled={pendingId === selected.id} onClick={() => void handleCancel(selected.id)}>Отказаться</button>
            </div>
          </BottomSheet>

          <BottomSheet open={registrationSuccess !== null} onClose={() => setRegistrationSuccess(null)} title="Место за вами">
            {registrationSuccess && (
              <div className="era-success-state" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: ".25rem" }}>
                  <strong style={{ fontSize: "var(--era-text-lg)" }}>{registrationSuccess.title}</strong>
                  <span style={{ color: "var(--era-text-muted)" }}>{formatDate(registrationSuccess.event_date)} · {registrationSuccess.event_time}</span>
                  <span style={{ color: "var(--era-text-muted)" }}>{registrationSuccess.location}</span>
                </div>
                <button type="button" className="era-btn-primary" onClick={() => addToCalendar(registrationSuccess)}>Добавить в календарь</button>
                <button type="button" onClick={() => setRegistrationSuccess(null)}>Готово</button>
              </div>
            )}
          </BottomSheet>
        </>
      );
    }
  }

  const scopeMeta = SCOPES.find((item) => item.value === scope) ?? SCOPES[0];

  return (
    <div className="era-page" style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
      <button type="button" onClick={() => setFilterOpen(true)} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>Показать: <strong>{scopeMeta.label}</strong></span><span>⌄</span>
      </button>

      {state.status === "loading" && <SkeletonList count={3} />}
      {state.status === "error" && <EmptyState text="Не удалось загрузить события. Попробуйте ещё раз чуть позже." />}
      {state.status === "ready" && state.data.length === 0 && (
        <EmptyState text="Пока нет событий в этом разделе. Как только появится новое мероприятие, оно будет здесь." />
      )}
      {state.status === "ready" && state.data.length > 0 && (
        <div className="era-stagger" style={{ display: "flex", flexDirection: "column", gap: ".8rem" }}>
          {state.data.map((event) => (
            <Card key={event.id} style={{ padding: "0.65rem", overflow: "hidden" }}>
              <EventPoster event={event} compact />
              <div style={{ padding: "0.7rem 0.3rem 0.2rem", display: "flex", flexDirection: "column", gap: "0.45rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", alignItems: "flex-start" }}>
                  <StatusBadge label={event.display_status} tone={ACTIVE_REGISTRATION_STATUSES.has(event.registration_status ?? "") ? "violet" : "neutral"} />
                  {event.points_for_visit > 0 && <strong style={{ fontSize: "0.82rem", color: "var(--era-gold-ink)" }}>+{event.points_for_visit} баллов</strong>}
                </div>
                <strong style={{ fontSize: "1.18rem", lineHeight: 1.15 }}>{event.title}</strong>
                <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.88rem" }}>{formatDate(event.event_date)} · {event.event_time}</p>
                <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.88rem" }}>📍 {event.location}</p>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", color: "var(--era-text-muted)", fontSize: "0.8rem" }}>
                  <span>{capacityText(event)}</span>
                  {event.remaining_count !== null && <span>Осталось {event.remaining_count}</span>}
                </div>
                <button type="button" className="era-btn-primary" onClick={() => openEvent(event.id)} style={{ width: "100%", marginTop: "0.25rem" }}>Открыть событие</button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <BottomSheet open={filterOpen} onClose={() => setFilterOpen(false)} title="Какие события показать?">
        <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
          {SCOPES.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => { setScope(option.value); setFilterOpen(false); }}
              style={{ textAlign: "left", padding: "0.85rem" }}
            >
              <strong>{option.label}</strong>
              <span style={{ display: "block", marginTop: 3, color: "var(--era-text-muted)", fontSize: "0.8rem" }}>{option.description}</span>
            </button>
          ))}
        </div>
      </BottomSheet>
    </div>
  );
}
