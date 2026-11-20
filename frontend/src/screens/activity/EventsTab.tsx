import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  cancelEventRegistration,
  describeActionError,
  downloadEventCalendar,
  downloadEventPoster,
  fetchEventActivities,
  fetchEvents,
  sendEventCalendarToChat,
  registerForEvent,
} from "../../api/client";
import { EventDetailsEditor } from "../admin/events/EventDetailsEditor";
import { BottomSheet } from "../../components/BottomSheet";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { MediaRequestButton } from "../../components/MediaRequestButton";
import { SkeletonList } from "../../components/Skeleton";
import { StatusBadge } from "../../components/StatusBadge";
import { TypographyFeedCard } from "../../components/TypographyFeedCard";
import { useToast } from "../../components/Toast";
import { useAsync } from "../../hooks/useAsync";
import { safeEvidenceUrl } from "../../utils/safeEvidenceUrl";
import { formatFeedDateLine } from "../../utils/feedDate";
import { getTelegramWebApp, successHaptic } from "../../telegram/webApp";
import type { EventActivity, EventItem, EventScope, EventSignup } from "../../types/activity";
import { AnniversaryRegistration } from "./AnniversaryRegistration";
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
  { value: "for_me", label: "Для меня", description: "Ближайшие события, ваши записи и лист ожидания" },
  { value: "all", label: "Все события", description: "Вся открытая афиша ЭРА" },
  { value: "mine", label: "Мои мероприятия", description: "Записи и лист ожидания" },
  { value: "past", label: "Прошедшие", description: "История мероприятий" },
];

function registrationBadgeTone(status: string | null | undefined): "violet" | "gold" | "neutral" {
  if (status === WAITLIST_STATUS) return "gold";
  if (ACTIVE_REGISTRATION_STATUSES.has(status ?? "")) return "violet";
  return "neutral";
}

function formatDate(value: string): string {
  const date = new Date(`${value}T00:00:00`);
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", weekday: "short" }).format(date);
}

function capacityText(event: EventItem): string {
  if (event.participant_limit === null) return "Без ограничения мест";
  return `${event.registered_count} / ${event.participant_limit} участников`;
}

/** Drop flyer lines already shown in КОГДА / ГДЕ / ОРГАНИЗАТОР so the card isn't doubled. */
export function cleanEventDescriptionBody(text: string, event: EventItem): string {
  const location = (event.location || "").trim().toLowerCase();
  const address = (event.address || "").trim().toLowerCase();
  const organizer = (event.organizer || "").trim().toLowerCase();
  const title = (event.title || "").trim().toLowerCase();
  const dateBits = [
    event.event_date,
    event.event_time,
    event.end_time,
    formatDate(event.event_date).toLowerCase(),
  ].filter(Boolean).map(String);
  const looksLikeMetaLine = (lower: string, stripped: string): boolean => {
    if (/^(когда|где|время|дата|место|адрес|организатор)\b/i.test(stripped)) return true;
    if (title && (lower === title || lower === `«${title}»` || lower === `"${title}"` || stripped === title)) return true;
    if (location && lower.includes(location) && lower.length < location.length + 28) return true;
    if (address && lower.includes(address) && lower.length < address.length + 28) return true;
    if (organizer && (lower === organizer || stripped === organizer || lower.startsWith(`${organizer} ·`) || stripped.startsWith("организатор"))) return true;
    if (dateBits.some((bit) => bit && lower.includes(bit.toLowerCase()) && lower.length < 56)) return true;
    return false;
  };

  const cleaned = text
    .split(/\r?\n/)
    .filter((raw) => {
      const line = raw.trim();
      if (!line) return true;
      const lower = line.toLowerCase().replace(/\s+/g, " ");
      const stripped = lower.replace(/^[\p{Emoji_Presentation}\p{Extended_Pictographic}\s•\-–—]+/u, "");
      // Only drop calendar/pin/time flyer lines when they actually repeat structured meta.
      // Do not delete ✅/💚/etc. instruction lines just because they start with an emoji.
      if (/^[📅🗓⏰🕒🕐🕑🕓🕔🕕🕖🕗🕘🕙🕚🕛📍📌🏠🏢🗺]/u.test(line) && looksLikeMetaLine(lower, stripped)) return false;
      if (looksLikeMetaLine(lower, stripped)) return false;
      return true;
    })
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  return cleaned;
}

// Calendar times are stored as local Asia/Yerevan clock times. Build explicit UTC
// instants for Google Calendar without depending on the participant's device TZ.
function googleCalendarUrl(event: EventItem): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(event.event_date)) return null;
  const timePattern = /^\d{2}:\d{2}(?::\d{2})?$/;
  if (!timePattern.test(event.event_time)) return null;
  const asInstant = (clock: string) => new Date(
    `${event.event_date}T${clock.length === 5 ? `${clock}:00` : clock}+04:00`,
  );
  const start = asInstant(event.event_time);
  if (!Number.isFinite(start.getTime())) return null;
  const end = event.end_time && timePattern.test(event.end_time)
    ? asInstant(event.end_time)
    : new Date(start.getTime() + 60 * 60 * 1000);
  if (!Number.isFinite(end.getTime())) return null;
  if (end <= start) end.setUTCDate(end.getUTCDate() + 1);
  const stamp = (date: Date) => date.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: event.title,
    dates: `${stamp(start)}/${stamp(end)}`,
    ctz: "Asia/Yerevan",
    details: event.full_description || event.description || "",
    location: [event.location, event.address].filter(Boolean).join(", "),
  });
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

function isIosDevice(): boolean {
  return /iPad|iPhone|iPod/i.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

function EventCalendarButton({ event }: { event: EventItem }) {
  const [busy, setBusy] = useState(false);
  const [preparedFile, setPreparedFile] = useState<File | null>(null);
  const [preparingShare, setPreparingShare] = useState(isIosDevice());
  const toast = useToast();
  const googleUrl = googleCalendarUrl(event);
  const ios = isIosDevice();

  useEffect(() => {
    if (!ios) return;
    let active = true;
    setPreparedFile(null);
    setPreparingShare(true);
    // Web Share must be called directly from a tap. Fetching the protected ICS
    // inside that tap can lose transient user activation on iOS Telegram, so
    // prepare the file read-only while the event detail is already visible.
    const probe = new File([""], "ERA.ics", { type: "text/calendar" });
    let canShareFile = false;
    try {
      canShareFile = typeof navigator.share === "function"
        && typeof navigator.canShare === "function"
        && navigator.canShare({ files: [probe] });
    } catch { /* unsupported WebView */ }
    if (!canShareFile) {
      setPreparingShare(false);
      return () => { active = false; };
    }
    void downloadEventCalendar(event.id)
      .then((blob) => {
        if (active) setPreparedFile(new File([blob], `ERA-${event.id}.ics`, { type: "text/calendar" }));
      })
      .catch(() => { /* explain unavailable import on explicit tap */ })
      .finally(() => { if (active) setPreparingShare(false); });
    return () => { active = false; };
  }, [event.id, ios]);

  async function shareAppleCalendar() {
    if (busy || preparingShare) return;
    if (ios) {
      if (!preparedFile || typeof navigator.share !== "function") {
        toast.show("Telegram на iPhone не поддерживает передачу .ics. Используйте Google Календарь или откройте ЭРА в Safari.", "error");
        return;
      }
      try {
        // No await before share: preserve the user gesture on iOS.
        await navigator.share({ files: [preparedFile], title: event.title });
        toast.show("Выберите Календарь или «Сохранить в Файлы» в меню «Поделиться».");
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        toast.show("Не удалось открыть меню «Поделиться». Используйте Google Календарь.", "error");
      }
      return;
    }
    setBusy(true);
    try {
      const blob = await downloadEventCalendar(event.id);
      const file = new File([blob], `ERA-${event.id}.ics`, { type: "text/calendar" });
      const url = URL.createObjectURL(file);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = file.name;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
      toast.show("Скачан .ics. Откройте файл в календаре; после изменения события скачайте новую версию.");
    } catch {
      toast.show("Не удалось скачать календарь. Попробуйте Google Календарь.", "error");
    } finally {
      setBusy(false);
    }
  }

  async function sendToChat() {
    if (busy) return;
    setBusy(true);
    try {
      await sendEventCalendarToChat(event.id);
      toast.show("Файл календаря отправлен вам в чат с ботом ЭРА.");
    } catch {
      toast.show("Отправка не подтверждена. Проверьте чат с ботом; альтернативно используйте Google Календарь.", "error");
    } finally {
      setBusy(false);
    }
  }

  function openGoogle(eventClick: React.MouseEvent<HTMLAnchorElement>) {
    if (!googleUrl) return;
    const telegram = getTelegramWebApp();
    if (telegram?.openLink) {
      try {
        telegram.openLink(googleUrl);
        eventClick.preventDefault();
      } catch { /* fall back to the normal external anchor */ }
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: ".5rem" }}>
      {googleUrl && <a href={googleUrl} target="_blank" rel="noopener noreferrer" onClick={openGoogle}
        className="era-btn-primary" style={{ textAlign: "center", textDecoration: "none", padding: ".75rem", borderRadius: "var(--era-radius-control)" }}>
        Google Календарь
      </a>}
      <button type="button" disabled={busy || preparingShare} onClick={() => void shareAppleCalendar()}>
        {busy || preparingShare ? "Готовим файл…" : "Календарь Apple (.ics)"}
      </button>
      {ios && <button type="button" disabled={busy} onClick={() => void sendToChat()}>
        {busy ? "Отправляем…" : "Получить файл календаря в чате ЭРА"}
      </button>}
      <small style={{ color: "var(--era-text-muted)" }}>
        На iPhone используйте системное меню «Поделиться». Если оно недоступно, выберите Google Календарь.
        {event.end_time ? "" : " Если время окончания не указано, Google предложит длительность 1 час."}
      </small>
    </div>
  );
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
      {state.data.map((activity: EventActivity) => {
        const submitUrl = safeEvidenceUrl(activity.submit_deep_link);
        return (
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
          {submitUrl && (
            <a
              href={submitUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="era-btn-primary"
              style={{ textAlign: "center", textDecoration: "none", marginTop: "0.35rem", minHeight: 44, display: "grid", placeItems: "center", borderRadius: "var(--era-radius-control)" }}
            >
              Отправить результат
            </a>
          )}
        </div>
        );
      })}
    </div>
  );
}

export function EventPoster({ event, compact = false }: { event: EventItem; compact?: boolean }) {
  // Compact feed: full-bleed cover in a fixed frame (no letterbox gaps).
  // Detail: contain so the full flyer stays readable.
  const height = compact ? 180 : 245;
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let alive = true;
    setSrc(null);
    if (!event.poster_url) {
      return () => {
        alive = false;
      };
    }
    // Public /event-posters/{id} denies CANCELLED. Use authenticated /events/{id}/poster
    // so registered «Прошедшие» history keeps the afisha (Codex P2 on #691).
    void downloadEventPoster(event.id)
      .then((blob) => {
        if (!alive) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      })
      .catch(() => {
        if (!alive) return;
        if (event.status === "cancelled") {
          setSrc(null);
          return;
        }
        setSrc(`${API_BASE_URL}/api/v1/event-posters/${event.id}`);
      });
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [event.id, event.poster_url, event.status]);

  if (src) {
    return (
      <div
        style={{
          width: "100%",
          height: compact ? height : undefined,
          maxHeight: compact ? undefined : "70vh",
          borderRadius: compact ? "0.85rem" : "1.25rem",
          background: "var(--era-surface-2)",
          overflow: "hidden",
          display: "grid",
          placeItems: "center",
        }}
      >
        <img
          src={src}
          alt={`Афиша ${event.title}`}
          style={{
            width: "100%",
            height: compact ? "100%" : "auto",
            maxHeight: compact ? undefined : "70vh",
            objectFit: compact ? "cover" : "contain",
            objectPosition: "center top",
            display: "block",
          }}
        />
      </div>
    );
  }
  return (
    <div
      aria-hidden="true"
      style={{
        height,
        borderRadius: compact ? "0.85rem" : "1.25rem",
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
  openSignup?: boolean;
  event: EventItem;
  pending: boolean;
  actionError: string | null;
  onRegister: (fields?: EventSignup) => void;
  onCancelRequest: () => void;
  onBack: () => void;
}

function EventDetail({ event, openSignup, pending, actionError, onRegister, onCancelRequest, onBack }: EventDetailProps) {
  const [showForm, setShowForm] = useState(Boolean(openSignup && event.signup_defaults));
  const [formError, setFormError] = useState<string | null>(null);
  const anniversary = event.anniversary_registered != null;
  const registered = ACTIVE_REGISTRATION_STATUSES.has(event.registration_status ?? "");
  const waitlisted = event.registration_status === WAITLIST_STATUS;
  const chatUrl = safeEvidenceUrl(event.chat_url);
  const externalSignupUrl = !event.registration_required && event.contact?.startsWith("https://t.me/")
    ? safeEvidenceUrl(event.contact) : null;
  const rawDescription = (event.full_description || event.description || event.short_description || "").trim();
  const summary = event.short_description?.trim() || "";
  const cleanedBody = cleanEventDescriptionBody(rawDescription, event);
  // One text block only — never stack short + full (they often repeat the flyer).
  const bodyText = cleanedBody || summary;

  return (
    <div className="era-page" style={{ display: "flex", flexDirection: "column", gap: "0.75rem", paddingBottom: "calc(10.25rem + env(safe-area-inset-bottom, 0px))" }}>
      <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← К событиям</button>
      <EventPoster event={event} />

      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <StatusBadge label={event.display_status} tone={registrationBadgeTone(event.registration_status)} />
        <h2 style={{ fontSize: "clamp(1.65rem, 7vw, 2.35rem)", lineHeight: 1.05, margin: 0, overflowWrap: "anywhere", textWrap: "balance" }}>{event.title}</h2>
      </div>

      <Card style={{ padding: "0.95rem" }}>
        <div style={{ display: "grid", gap: "0.75rem" }}>
          <div><span style={{ color: "var(--era-text-muted)", fontSize: "0.78rem" }}>КОГДА</span><div style={{ fontWeight: 800, marginTop: 2 }}>{formatDate(event.event_date)} · {event.event_time}{event.end_time ? `–${event.end_time}` : ""}</div></div>
          <div>
            <span style={{ color: "var(--era-text-muted)", fontSize: "0.78rem" }}>ГДЕ</span>
            {safeEvidenceUrl(event.location) ? (
              <a href={safeEvidenceUrl(event.location)!} target="_blank" rel="noopener noreferrer" className="era-btn-secondary" style={{ display: "inline-flex", marginTop: ".35rem", textDecoration: "none" }}>Открыть место</a>
            ) : <div style={{ fontWeight: 800, marginTop: 2 }}>{event.location}</div>}
            {event.address && <div style={{ color: "var(--era-text-muted)", fontSize: "0.85rem" }}>{event.address}</div>}
          </div>
          {event.organizer && <div><span style={{ color: "var(--era-text-muted)", fontSize: "0.78rem" }}>ОРГАНИЗАТОР</span><div style={{ fontWeight: 800, marginTop: 2 }}>{event.organizer}</div></div>}
        </div>
      </Card>

      {bodyText && (
        <Card>
          <h3 style={{ margin: "0 0 .55rem", fontSize: "1.05rem" }}>О событии</h3>
          <div className="era-readable-copy">
            {bodyText.split(/\r?\n(?:[^\S\r\n]*\r?\n)+/).map((paragraph, index) => (
              <p key={index} style={{ margin: index === 0 ? 0 : ".75rem 0 0" }}>{paragraph.trim()}</p>
            ))}
          </div>
        </Card>
      )}

      {event.participant_value && (
        <Card style={{ background: "linear-gradient(145deg, rgba(188, 33, 132,.14), rgba(255, 165, 234,.06))" }}>
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
      <EventCalendarButton event={event} />
      {chatUrl && <a href={chatUrl} target="_blank" rel="noopener noreferrer" className="era-btn-secondary" style={{ textAlign: "center", textDecoration: "none" }}>Открыть чат</a>}
      {!externalSignupUrl && safeEvidenceUrl(event.contact) ? (
        <a href={safeEvidenceUrl(event.contact)!} target="_blank" rel="noopener noreferrer" className="era-btn-secondary" style={{ textAlign: "center", textDecoration: "none" }}>Открыть ссылку</a>
      ) : !externalSignupUrl && event.contact ? <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.86rem" }}>Связь: {event.contact}</p> : null}
      <MediaRequestButton sourceType="event" sourceId={event.id} />
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
              Лист ожидания · место не закреплено
            </div>
            <button type="button" disabled={pending} onClick={onCancelRequest} style={{ minWidth: 106 }}>Покинуть</button>
          </div>
        ) : externalSignupUrl ? (
          <a href={externalSignupUrl} target="_blank" rel="noopener noreferrer" className="era-btn-primary"
            style={{ display: "grid", placeItems: "center", minHeight: 48, textDecoration: "none" }}>
            Записаться по ссылке ↗
          </a>
        ) : anniversary ? (
          <AnniversaryRegistration key={event.id} event={event} />
        ) : event.can_register && event.signup_defaults && showForm ? (
          <form style={{ display: "grid", gap: 10, maxHeight: "58dvh", overflowY: "auto", paddingBottom: 8 }} onSubmit={e => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            const fullName = String(data.get("full_name") ?? "").trim().replace(/\s+/g, " ");
            const organization = String(data.get("organization") ?? "").trim();
            const phone = String(data.get("phone") ?? "").trim();
            if (fullName.split(" ").filter(Boolean).length < 3) {
              setFormError("Добавьте отчество: для регистрации нужны фамилия, имя и отчество полностью.");
              return;
            }
            if (phone.replace(/\D/g, "").length < 7) {
              setFormError("Проверьте номер телефона: не менее семи цифр.");
              return;
            }
            if (organization.length < 2) {
              setFormError("Укажите полное название организации или учебного заведения.");
              return;
            }
            setFormError(null);
            onRegister({ full_name: fullName, phone, organization });
          }}>
            <label>Фамилия, имя и отчество
              <input required name="full_name" autoComplete="name" maxLength={255} defaultValue={event.signup_defaults.full_name} onChange={() => setFormError(null)} />
              <small style={{ display: "block", color: "var(--era-text-muted)", marginTop: 4 }}>
                Все три части без сокращений. Например: Иванова Анна Сергеевна.
              </small>
            </label>
            <label>Полное название вуза или организации
              <input required name="organization" maxLength={255} defaultValue={event.signup_defaults.organization} onChange={() => setFormError(null)} />
              <small style={{ display: "block", color: "var(--era-text-muted)", marginTop: 4 }}>
                Не аббревиатура: укажите полное официальное название.
              </small>
            </label>
            <label>Номер телефона<input required type="tel" autoComplete="tel" inputMode="tel" name="phone" maxLength={32} defaultValue={event.signup_defaults.phone} onChange={() => setFormError(null)} /></label>
            <small>Данные доступны только организаторам мероприятия.</small>
            {formError && <p role="alert" style={{ color: "var(--era-error)", margin: 0 }}>{formError}</p>}
            <button type="submit" className="era-btn-primary" disabled={pending}>{pending ? "Регистрируем…" : "Подтвердить регистрацию"}</button>
            <button type="button" disabled={pending} onClick={() => { setFormError(null); setShowForm(false); }}>Назад</button>
          </form>
        ) : event.can_register ? (
          <button type="button" className="era-btn-primary" disabled={pending} onClick={() => event.signup_defaults ? setShowForm(true) : onRegister()} style={{ width: "100%" }}>
            {pending ? "● Сохраняем…" : event.remaining_count === 0 && event.waitlist_enabled ? "Встать в лист ожидания" : "Участвовать"}
          </button>
        ) : (
          <button type="button" disabled style={{ width: "100%" }}>
            {!event.registration_required
              ? "Регистрация не нужна"
              : event.display_status || "Регистрация недоступна"}
          </button>
        )}
      </div>
    </div>
  );
}

interface EventsTabProps {
  canEdit?: boolean;
  initialItemId?: number | null;
  initialScope?: EventScope;
}

export function EventsTab({ initialItemId, initialScope, canEdit }: EventsTabProps = {}) {
  const [editing, setEditing] = useState(false);
  const [scope, setScope] = useState<EventScope>(initialItemId ? "all" : initialScope ?? "for_me");
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchEvents(scope), [scope, refreshKey]);
  const [selectedId, setSelectedId] = useState<number | null>(initialItemId ?? null);
  const [selectedOverride, setSelectedOverride] = useState<EventItem | null>(null);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const pendingRegistration = useRef(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [cancelTarget, setCancelTarget] = useState<EventItem | null>(null);
  const [registrationSuccess, setRegistrationSuccess] = useState<EventItem | null>(null);
  const [waitlistSuccess, setWaitlistSuccess] = useState<EventItem | null>(null);
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

  const handleRegister = useCallback(async (eventId: number, fields?: EventSignup) => {
    if (pendingRegistration.current) return;
    pendingRegistration.current = true;
    setPendingId(eventId);
    setActionError(null);
    try {
      const result = await registerForEvent(eventId, fields);
      setSelectedOverride(result);
      refresh();
      if (result.registration_status === WAITLIST_STATUS) {
        setWaitlistSuccess(result);
        toast.show("Вы в листе ожидания — место ещё не закреплено", "success");
      } else {
        successHaptic();
        setRegistrationSuccess(result);
        toast.show("Место за вами", "success");
      }
    } catch (error) {
      const description = describeActionError(error);
      setActionError(description);
      toast.show(description, "error");
    } finally {
      pendingRegistration.current = false;
      setPendingId(null);
    }
  }, [refresh, toast]);

  const handleCancel = useCallback(async (eventId: number) => {
    setPendingId(eventId);
    setActionError(null);
    const leavingWaitlist = cancelTarget?.registration_status === WAITLIST_STATUS;
    try {
      const result = await cancelEventRegistration(eventId);
      setSelectedOverride(result);
      refresh();
      toast.show(leavingWaitlist ? "Вы покинули лист ожидания" : "Участие отменено", "info");
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setPendingId(null);
      setCancelTarget(null);
    }
  }, [cancelTarget, refresh, toast]);

  const openEvent = (id: number) => {
    setSelectedId(id);
    setSelectedOverride(null);
    setActionError(null);
    setRegistrationSuccess(null);
    setWaitlistSuccess(null);
    window.location.hash = `#/events/${id}`;
  };

  const closeEvent = () => {
    setSelectedId(null);
    setSelectedOverride(null);
    setActionError(null);
    setRegistrationSuccess(null);
    setWaitlistSuccess(null);
    setScope("for_me");
    window.location.hash = "#/events";
  };

  const registrationPrompt = (
    <>
      <BottomSheet open={registrationSuccess !== null} onClose={() => setRegistrationSuccess(null)} title="Место за вами">
        {registrationSuccess && (
          <div className="era-success-state" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: ".25rem" }}>
              <strong style={{ fontSize: "var(--era-text-lg)" }}>{registrationSuccess.title}</strong>
              <span style={{ color: "var(--era-text-muted)" }}>{formatDate(registrationSuccess.event_date)} · {registrationSuccess.event_time}</span>
              <span style={{ color: "var(--era-text-muted)" }}>{registrationSuccess.location}</span>
            </div>
            <EventCalendarButton event={registrationSuccess} />
            <a href="#/events/mine" onClick={() => setRegistrationSuccess(null)}>Мои мероприятия</a>
            <button type="button" onClick={() => setRegistrationSuccess(null)}>Готово</button>
          </div>
        )}
      </BottomSheet>
      <BottomSheet open={waitlistSuccess !== null} onClose={() => setWaitlistSuccess(null)} title="Вы в листе ожидания">
        {waitlistSuccess && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <p style={{ margin: 0, color: "var(--era-text-muted)" }}>
              Сейчас свободных мест нет. Место ещё не закреплено — если оно освободится, бот сообщит вам автоматически.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: ".25rem" }}>
              <strong style={{ fontSize: "var(--era-text-lg)" }}>{waitlistSuccess.title}</strong>
              <span style={{ color: "var(--era-text-muted)" }}>{formatDate(waitlistSuccess.event_date)} · {waitlistSuccess.event_time}</span>
            </div>
            <a href="#/events/mine" onClick={() => setWaitlistSuccess(null)}>Мои мероприятия</a>
            <button type="button" onClick={() => setWaitlistSuccess(null)}>Понятно</button>
          </div>
        )}
      </BottomSheet>
    </>
  );

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
      if (canEdit && editing) {
        return <EventDetailsEditor key={selected.id} eventId={selected.id} onClose={() => {
          setEditing(false);
          setSelectedOverride(null);
          refresh();
        }} />;
      }
      return (
        <>
          {canEdit && <button onClick={() => setEditing(true)}>Редактировать мероприятие</button>}
          <EventDetail
            key={selected.id}
            openSignup={selected.id === initialItemId}
            event={selected}
            pending={pendingId === selected.id}
            actionError={actionError}
            onRegister={(fields) => void handleRegister(selected.id, fields)}
            onCancelRequest={() => setCancelTarget(selected)}
            onBack={closeEvent}
          />

          <BottomSheet
            open={cancelTarget !== null}
            onClose={() => setCancelTarget(null)}
            title={cancelTarget?.registration_status === WAITLIST_STATUS ? "Покинуть лист ожидания?" : "Отказаться от участия?"}
          >
            <p style={{ color: "var(--era-text-muted)", margin: "0 0 1rem" }}>
              {cancelTarget?.registration_status === WAITLIST_STATUS
                ? "Вы уйдёте из очереди. Место вам ещё не было закреплено — вернуться можно, если регистрация и лист ожидания всё ещё открыты."
                : "Место освободится для участника из листа ожидания. Вернуться можно будет только если регистрация всё ещё открыта."}
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
              <button type="button" onClick={() => setCancelTarget(null)}>
                {cancelTarget?.registration_status === WAITLIST_STATUS ? "Остаться в очереди" : "Остаться"}
              </button>
              <button type="button" className="era-btn-primary" disabled={pendingId === selected.id} onClick={() => void handleCancel(selected.id)}>
                {cancelTarget?.registration_status === WAITLIST_STATUS ? "Покинуть" : "Отказаться"}
              </button>
            </div>
          </BottomSheet>

          {registrationPrompt}
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
      {state.status === "error" && (
        <>
          <EmptyState text="Не удалось загрузить события." />
          <button type="button" onClick={refresh}>Повторить загрузку</button>
        </>
      )}
      {state.status === "ready" && state.data.length === 0 && (
        <EmptyState
          text={
            scope === "mine"
              ? "Пока нет ваших записей. Запишитесь на событие в афише — оно появится здесь, в том числе из листа ожидания."
              : scope === "past"
                ? "Прошедших мероприятий пока нет."
                : "Пока нет событий в этом разделе. Как только появится новое мероприятие, оно будет здесь."
          }
        />
      )}
      {state.status === "ready" && state.data.length > 0 && (
        <div className="era-stagger" style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
          {state.data.map((event) => (
            <TypographyFeedCard
              key={event.id}
              title={event.title}
              dateLine={formatFeedDateLine({
                date: event.event_date,
                time: event.event_time,
                endTime: event.end_time,
              })}
              onClick={() => openEvent(event.id)}
            />
          ))}
        </div>
      )}

      {registrationPrompt}
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
