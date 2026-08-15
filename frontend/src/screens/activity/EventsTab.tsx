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
import { EventCard } from "../../components/EventCard";
import { PageHeader } from "../../components/PageHeader";
import { PrimaryButton, SecondaryButton } from "../../components/Buttons";
import { SkeletonList } from "../../components/Skeleton";
import { StatusBadge } from "../../components/StatusBadge";
import { useToast } from "../../components/Toast";
import { CalendarIcon, FilterIcon, MapPinIcon, ShareIcon } from "../../components/icons";
import { useAsync } from "../../hooks/useAsync";
import type { EventActivity, EventItem, EventScope } from "../../types/activity";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const ACTIVE = new Set(["registered", "will_come", "attended"]);
const SCOPES: { value: EventScope; label: string }[] = [
  { value: "for_me", label: "Для меня" },
  { value: "all", label: "Все события" },
  { value: "mine", label: "Мои регистрации" },
  { value: "past", label: "Прошедшие" },
];

function todayIso(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function formatDate(value: string): string {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", weekday: "short" }).format(date);
}

function posterSrc(event: EventItem): string | null {
  return event.poster_url ? `${API_BASE_URL}/api/v1/event-posters/${event.id}` : null;
}

function addToCalendar(event: EventItem): void {
  const compact = (value: string) => value.replace(/[-:]/g, "");
  const start = `${compact(event.event_date)}T${compact(event.event_time)}00`;
  const end = `${compact(event.event_date)}T${compact(event.end_time ?? event.event_time)}00`;
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
  const url = URL.createObjectURL(new Blob([ics], { type: "text/calendar;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `ERA-${event.id}.ics`;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 500);
}

function openMap(event: EventItem): void {
  const query = [event.location, event.address].filter(Boolean).join(", ");
  if (!query) return;
  window.open(`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`, "_blank", "noopener,noreferrer");
}

async function shareEvent(event: EventItem): Promise<void> {
  const url = `${window.location.origin}${window.location.pathname}#/events/${event.id}`;
  const text = `${event.title} · ${event.event_date} ${event.event_time}`;
  if (navigator.share) {
    await navigator.share({ title: event.title, text, url });
    return;
  }
  window.open(`https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`, "_blank", "noopener,noreferrer");
}

function EventActivitiesPanel({ eventId }: { eventId: number }) {
  const state = useAsync(() => fetchEventActivities(eventId), [eventId]);
  if (state.status === "loading") return <SkeletonList count={1} />;
  if (state.status === "error") return <EmptyState title="Задания не загрузились" description="Регистрация сохранена; дополнительные активности можно открыть позже." />;
  if (state.data.length === 0) return null;
  return (
    <section className="era-section">
      <h3 style={{ margin: 0, fontSize: "var(--era-text-lg)" }}>Активности после события</h3>
      {state.data.map((activity: EventActivity) => (
        <Card key={activity.id} style={{ boxShadow: "none" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem" }}><strong>{activity.title}</strong><strong style={{ color: "var(--era-red)", whiteSpace: "nowrap" }}>+{activity.points}</strong></div>
          <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)" }}>{activity.description}</p>
          {activity.my_status && <p style={{ margin: "0.45rem 0 0", fontSize: "var(--era-text-xs)", color: "var(--era-text-muted)" }}>Статус: {activity.my_status}</p>}
          {activity.submit_deep_link && <a href={activity.submit_deep_link} target="_blank" rel="noreferrer" className="era-btn-secondary" style={{ marginTop: "0.7rem" }}>Отправить результат</a>}
        </Card>
      ))}
    </section>
  );
}

export function EventsTab({ initialItemId = null }: { initialItemId?: number | null }) {
  const [scope, setScope] = useState<EventScope>(initialItemId ? "all" : "for_me");
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchEvents(scope), [scope, refreshKey]);
  const [filterOpen, setFilterOpen] = useState(false);
  const [formatFilter, setFormatFilter] = useState<string>("all");
  const [onlyAvailable, setOnlyAvailable] = useState(false);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [selectedOverride, setSelectedOverride] = useState<EventItem | null>(null);
  const [cancelTarget, setCancelTarget] = useState<EventItem | null>(null);
  const [successEvent, setSuccessEvent] = useState<EventItem | null>(null);
  const toast = useToast();

  useEffect(() => {
    if (initialItemId) setScope("all");
  }, [initialItemId]);

  const events = state.status === "ready" ? state.data : [];
  const selected = initialItemId !== null
    ? selectedOverride?.id === initialItemId ? selectedOverride : events.find((event) => event.id === initialItemId) ?? null
    : null;

  const formats = useMemo(() => Array.from(new Set(events.map((event) => event.format).filter(Boolean))).sort(), [events]);
  const filtered = useMemo(() => events.filter((event) => {
    if (formatFilter !== "all" && event.format !== formatFilter) return false;
    if (onlyAvailable && !event.can_register && !ACTIVE.has(event.registration_status ?? "")) return false;
    return true;
  }), [events, formatFilter, onlyAvailable]);

  const refresh = useCallback(() => setRefreshKey((value) => value + 1), []);

  const register = useCallback(async (event: EventItem) => {
    if (pendingId !== null) return;
    setPendingId(event.id);
    setActionError(null);
    try {
      const result = await registerForEvent(event.id);
      setSelectedOverride(result);
      setSuccessEvent(result);
      refresh();
      toast.show(result.registration_status === "waitlist" ? "Вы в листе ожидания" : "Место за вами", "success");
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setPendingId(null);
    }
  }, [pendingId, refresh, toast]);

  const cancel = useCallback(async (event: EventItem) => {
    if (pendingId !== null) return;
    setPendingId(event.id);
    setActionError(null);
    try {
      const result = await cancelEventRegistration(event.id);
      setSelectedOverride(result);
      setCancelTarget(null);
      setSuccessEvent(null);
      refresh();
      toast.show("Участие отменено", "info");
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setPendingId(null);
    }
  }, [pendingId, refresh, toast]);

  if (initialItemId !== null) {
    if (state.status === "loading") return <SkeletonList count={3} />;
    if (state.status === "error" || !selected) {
      return <><PageHeader title="Событие" onBack={() => window.location.hash = "#/events"} /><EmptyState title="Это событие больше недоступно" description="Возможно, его удалили или доступ изменился." actionLabel="Вернуться к событиям" onAction={() => window.location.hash = "#/events"} /></>;
    }
    return (
      <EventDetail
        event={selected}
        pending={pendingId === selected.id}
        actionError={actionError}
        onRegister={() => void register(selected)}
        onCancel={() => setCancelTarget(selected)}
      >
        <BottomSheet open={Boolean(cancelTarget)} onClose={() => setCancelTarget(null)} title="Отказаться от участия?">
          <p style={{ margin: 0, color: "var(--era-text-muted)" }}>Место освободится для другого участника. Если передумали — просто останьтесь зарегистрированы.</p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.55rem", marginTop: "1rem" }}>
            <SecondaryButton onClick={() => setCancelTarget(null)}>Остаться</SecondaryButton>
            <button type="button" className="era-btn-danger" disabled={pendingId !== null} onClick={() => cancelTarget && void cancel(cancelTarget)}>{pendingId ? "Отменяем…" : "Отказаться"}</button>
          </div>
        </BottomSheet>
        <BottomSheet open={Boolean(successEvent)} onClose={() => setSuccessEvent(null)} title={successEvent?.registration_status === "waitlist" ? "Вы в листе ожидания" : "Место за вами"}>
          {successEvent && <>
            <Card style={{ boxShadow: "none" }}><strong>{formatDate(successEvent.event_date)} · {successEvent.event_time}</strong><p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)" }}>{successEvent.location}{successEvent.address ? ` · ${successEvent.address}` : ""}</p></Card>
            <div style={{ display: "grid", gap: "0.55rem", marginTop: "0.75rem" }}>
              <SecondaryButton onClick={() => addToCalendar(successEvent)}><CalendarIcon width={18} height={18} />Добавить в календарь</SecondaryButton>
              {successEvent.chat_url && <a href={successEvent.chat_url} target="_blank" rel="noreferrer" className="era-btn-secondary">Открыть чат</a>}
              {ACTIVE.has(successEvent.registration_status ?? "") && <button type="button" className="era-btn-danger" onClick={() => { setSuccessEvent(null); setCancelTarget(successEvent); }}>Отказаться от участия</button>}
            </div>
            <p style={{ margin: "0.75rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>Подробности и выбранные администратором напоминания придут в бот.</p>
          </>}
        </BottomSheet>
      </EventDetail>
    );
  }

  const today = todayIso();
  const todayItems = filtered.filter((event) => event.event_date === today);
  const soonItems = filtered.filter((event) => event.event_date > today);
  const pastItems = filtered.filter((event) => event.event_date < today);
  const primaryList = scope === "past" ? pastItems : soonItems;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <button type="button" onClick={() => setFilterOpen(true)} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%", padding: "0.7rem 0.85rem" }}>
        <span><strong>{SCOPES.find((item) => item.value === scope)?.label}</strong><span style={{ display: "block", marginTop: 2, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", textAlign: "left" }}>{formatFilter === "all" ? "Все форматы" : formatFilter}{onlyAvailable ? " · есть места" : ""}</span></span>
        <FilterIcon width={20} height={20} style={{ color: "var(--era-red)" }} />
      </button>

      <BottomSheet open={filterOpen} onClose={() => setFilterOpen(false)} title="Фильтры событий">
        <p className="era-kicker">Показывать</p>
        <div style={{ display: "grid", gap: "0.4rem", marginTop: "0.5rem" }}>{SCOPES.map((item) => <button key={item.value} type="button" onClick={() => setScope(item.value)} style={{ textAlign: "left", background: scope === item.value ? "var(--era-tint-red)" : "#fff", borderColor: scope === item.value ? "rgba(227,38,54,.2)" : "var(--era-border)" }}>{item.label}</button>)}</div>
        {formats.length > 0 && <><p className="era-kicker" style={{ marginTop: "1rem" }}>Формат</p><select value={formatFilter} onChange={(event) => setFormatFilter(event.target.value)} style={{ marginTop: "0.5rem" }}><option value="all">Все форматы</option>{formats.map((format) => <option key={format} value={format}>{format}</option>)}</select></>}
        <label style={{ display: "flex", alignItems: "center", gap: "0.65rem", minHeight: 44, marginTop: "0.75rem" }}><input type="checkbox" checked={onlyAvailable} onChange={(event) => setOnlyAvailable(event.target.checked)} />Только доступные для регистрации</label>
        <PrimaryButton onClick={() => setFilterOpen(false)} style={{ width: "100%", marginTop: "0.75rem" }}>Готово</PrimaryButton>
      </BottomSheet>

      {state.status === "loading" && <SkeletonList count={3} />}
      {state.status === "error" && <EmptyState title="События не загрузились" description="Проверьте соединение и откройте раздел снова." />}
      {state.status === "ready" && filtered.length === 0 && <EmptyState title="По этим фильтрам событий нет" description="Измените фильтр или вернитесь ко всей афише." actionLabel="Сбросить фильтры" onAction={() => { setScope("all"); setFormatFilter("all"); setOnlyAvailable(false); }} />}

      {state.status === "ready" && todayItems.length > 0 && <EventGroup title="Сегодня" events={todayItems} />}
      {state.status === "ready" && primaryList.length > 0 && <EventGroup title={scope === "past" ? "Прошедшие" : "Скоро"} events={primaryList} />}
      {state.status === "ready" && scope !== "past" && pastItems.length > 0 && <section className="era-section"><h2 className="era-section-title">Ранее</h2><SecondaryButton onClick={() => setScope("past")}>Посмотреть прошедшие</SecondaryButton></section>}
    </div>
  );
}

function EventGroup({ title, events }: { title: string; events: EventItem[] }) {
  return <section className="era-section"><h2 className="era-section-title">{title}</h2><div style={{ display: "grid", gap: "0.75rem" }}>{events.map((event) => <EventCard key={event.id} event={event} onClick={() => { window.location.hash = `#/events/${event.id}`; }} />)}</div></section>;
}

function EventDetail({ event, pending, actionError, onRegister, onCancel, children }: { event: EventItem; pending: boolean; actionError: string | null; onRegister: () => void; onCancel: () => void; children: React.ReactNode }) {
  const registered = ACTIVE.has(event.registration_status ?? "");
  const waitlisted = event.registration_status === "waitlist";
  const poster = posterSrc(event);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <PageHeader title={event.title} eyebrow="Событие ЭРА" subtitle={event.short_description ?? undefined} onBack={() => { if (window.history.length > 1) window.history.back(); else window.location.hash = "#/events"; }} />
      {poster ? <img src={poster} alt={`Афиша ${event.title}`} style={{ width: "100%", maxHeight: 360, objectFit: "cover", borderRadius: "var(--era-radius-card)" }} /> : <div aria-hidden="true" style={{ height: 190, borderRadius: "var(--era-radius-card)", background: "linear-gradient(145deg,#151619,#981b28)", display: "flex", alignItems: "flex-end", padding: "1.25rem", color: "#fff" }}><strong style={{ fontSize: "2rem" }}>ЭРА</strong></div>}

      <Card><div style={{ display: "grid", gap: "0.8rem" }}><Info label="Когда" value={`${formatDate(event.event_date)} · ${event.event_time}${event.end_time ? `–${event.end_time}` : ""}`} /><Info label="Где" value={[event.location, event.address].filter(Boolean).join(" · ")} />{event.organizer && <Info label="Организатор" value={event.organizer} />}<Info label="Места" value={event.participant_limit === null ? `${event.registered_count} зарегистрировано` : `${event.registered_count} из ${event.participant_limit} · ${event.remaining_count ?? 0} свободно`} /></div></Card>

      <Card><h2 style={{ margin: 0, fontSize: "var(--era-text-xl)" }}>О событии</h2><p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{event.full_description ?? event.description}</p></Card>
      {event.participant_value && <Card style={{ borderColor: "rgba(197,162,100,.24)" }}><p className="era-kicker" style={{ color: "var(--era-gold-ink)" }}>Что вы получите</p><p style={{ margin: "0.4rem 0 0", whiteSpace: "pre-wrap" }}>{event.participant_value}</p></Card>}

      {event.program.length > 0 && <section className="era-section"><h2 className="era-section-title">Программа</h2>{event.program.map((item, index) => <Card key={`${item.title}-${index}`} style={{ boxShadow: "none" }}><div style={{ display: "flex", gap: "0.75rem" }}>{item.time && <strong style={{ color: "var(--era-red)", minWidth: 52 }}>{item.time}</strong>}<div><strong>{item.title || `Активность ${index + 1}`}</strong>{item.description && <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>{item.description}</p>}{item.responsible && <p style={{ margin: "0.25rem 0 0", fontSize: "var(--era-text-xs)" }}>Ответственный: {item.responsible}</p>}</div></div></Card>)}</section>}

      {event.participant_tasks.length > 0 && <section className="era-section"><h2 className="era-section-title">Задания и баллы</h2>{event.participant_tasks.map((task, index) => <Card key={`${task.title}-${index}`} style={{ boxShadow: "none" }}><div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem" }}><strong>{task.title || `Задание ${index + 1}`}</strong>{typeof task.points === "number" && <strong style={{ color: "var(--era-red)" }}>+{task.points}</strong>}</div>{task.description && <p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)" }}>{task.description}</p>}</Card>)}</section>}

      {(registered || waitlisted) && <Card style={{ background: waitlisted ? "var(--era-tint-gold)" : "var(--era-tint-success)", boxShadow: "none" }}><StatusBadge label={waitlisted ? "Лист ожидания" : "Вы участвуете"} tone="neutral" /><p style={{ margin: "0.45rem 0 0", color: "var(--era-text-muted)" }}>{waitlisted ? "Если место освободится, бот сообщит вам." : "Подробности и напоминания придут в бот."}</p></Card>}
      {registered && <EventActivitiesPanel eventId={event.id} />}

      {actionError && <Card style={{ borderColor: "rgba(101,90,115,.18)", background: "rgba(101,90,115,.05)" }}><strong>Не получилось выполнить действие</strong><p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)" }}>{actionError}</p></Card>}

      <div style={{ display: "grid", gap: "0.55rem" }}>
        {!registered && !waitlisted && event.can_register && <PrimaryButton busy={pending} busyLabel="Регистрируем…" onClick={onRegister}>{event.waitlist_enabled && event.remaining_count === 0 ? "Встать в лист ожидания" : "Участвовать"}</PrimaryButton>}
        {registered && <button type="button" className="era-btn-danger" disabled={pending} onClick={onCancel}>Отказаться от участия</button>}
        <SecondaryButton onClick={() => addToCalendar(event)}><CalendarIcon width={18} height={18} />Добавить в календарь</SecondaryButton>
        {(event.address || event.location) && <SecondaryButton onClick={() => openMap(event)}><MapPinIcon width={18} height={18} />Показать место</SecondaryButton>}
        {event.chat_url && <a href={event.chat_url} target="_blank" rel="noreferrer" className="era-btn-secondary">Открыть чат</a>}
        <SecondaryButton onClick={() => void shareEvent(event)}><ShareIcon width={18} height={18} />Поделиться</SecondaryButton>
        {event.project_id && <SecondaryButton onClick={() => { window.location.hash = `#/projects/${event.project_id}`; }}>Открыть связанный проект</SecondaryButton>}
      </div>
      {children}
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) { return <div><span style={{ color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>{label}</span><strong style={{ display: "block", marginTop: 2 }}>{value}</strong></div>; }
