import type { EventItem } from "../types/activity";
import { Card } from "./Card";
import { CalendarIcon, ChevronRightIcon, MapPinIcon } from "./icons";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

function formatDate(value: string): string {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short" }).format(date);
}

export function EventCard({ event, onClick, featured = false }: { event: EventItem; onClick: () => void; featured?: boolean }) {
  const poster = event.poster_url ? `${API_BASE_URL}/api/v1/event-posters/${event.id}` : null;
  const registered = ["registered", "will_come", "attended"].includes(event.registration_status ?? "");
  return (
    <Card interactive onClick={onClick} ariaLabel={`${event.title}. Открыть событие`} style={{ padding: 0, overflow: "hidden" }}>
      {poster ? (
        <img src={poster} alt={`Афиша ${event.title}`} style={{ width: "100%", height: featured ? 184 : 128, objectFit: "cover", display: "block" }} />
      ) : (
        <div aria-hidden="true" style={{ height: featured ? 148 : 100, display: "flex", alignItems: "flex-end", padding: "1rem", background: "linear-gradient(145deg,#151619 0%,#981b28 100%)", color: "#fff" }}>
          <strong style={{ fontSize: featured ? "1.65rem" : "1.25rem", letterSpacing: "-.04em" }}>ЭРА</strong>
        </div>
      )}
      <div style={{ padding: "1rem" }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "0.75rem" }}>
          <div style={{ minWidth: 0 }}>
            <p className="era-kicker">{registered ? "Вы участвуете" : event.available_places}</p>
            <strong style={{ display: "block", marginTop: "0.3rem", fontSize: featured ? "var(--era-text-xl)" : "var(--era-text-lg)", lineHeight: 1.2, overflowWrap: "anywhere" }}>{event.title}</strong>
          </div>
          <ChevronRightIcon width={20} height={20} style={{ flexShrink: 0, color: "var(--era-text-muted)" }} />
        </div>
        <div style={{ marginTop: "0.75rem", display: "grid", gap: "0.4rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
          <span style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}><CalendarIcon width={16} height={16} />{formatDate(event.event_date)} · {event.event_time}</span>
          <span style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}><MapPinIcon width={16} height={16} />{event.location}</span>
        </div>
        {event.participant_limit !== null && <p style={{ margin: "0.7rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>{event.registered_count} из {event.participant_limit} мест занято{event.remaining_count !== null ? ` · свободно ${event.remaining_count}` : ""}</p>}
      </div>
    </Card>
  );
}
