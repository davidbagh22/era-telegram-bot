import type { EventItem } from "../types/activity";

const YEREVAN_OFFSET_HOURS = 4;

function toUtcStamp(date: string, time: string): string {
  const [y, m, d] = date.split("-").map(Number);
  const [hh, mm] = time.split(":").map(Number);
  const utc = new Date(Date.UTC(y, m - 1, d, hh - YEREVAN_OFFSET_HOURS, mm));
  return utc.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
}

export function googleCalendarUrl(event: EventItem): string {
  const start = toUtcStamp(event.event_date, event.event_time.slice(0, 5));
  let end = event.end_time ? toUtcStamp(event.event_date, event.end_time.slice(0, 5)) : "";
  if (!end || end <= start) {
    const base = new Date(Date.UTC(Number(start.slice(0, 4)), Number(start.slice(4, 6)) - 1,
      Number(start.slice(6, 8)), Number(start.slice(9, 11)) + 1, Number(start.slice(11, 13))));
    end = base.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  }
  const params = new URLSearchParams({
    action: "TEMPLATE", text: event.title, dates: `${start}/${end}`,
    details: event.short_description ?? event.description ?? "",
    location: [event.location, event.address].filter(Boolean).join(", "), ctz: "Asia/Yerevan",
  });
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

export function isIosWebView(userAgent: string = navigator.userAgent): boolean {
  return /iPhone|iPad|iPod/i.test(userAgent);
}
