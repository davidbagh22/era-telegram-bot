const MONTHS_RU = [
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

/** Parse date-only YYYY-MM-DD without constructing a timezone-sensitive Date. */
export function parseDateOnlyParts(value: string): { year: number; month: number; day: number } | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (!year || month < 1 || month > 12 || day < 1 || day > 31) return null;
  return { year, month, day };
}

function currentYerevanYear(): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Yerevan",
    year: "numeric",
  }).formatToParts(new Date());
  return Number(parts.find((part) => part.type === "year")?.value ?? new Date().getFullYear());
}

/** Current calendar date YYYY-MM-DD in Asia/Yerevan, independent of device TZ. */
export function yerevanTodayIso(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Yerevan",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const year = parts.find((part) => part.type === "year")?.value;
  const month = parts.find((part) => part.type === "month")?.value;
  const day = parts.find((part) => part.type === "day")?.value;
  if (year && month && day) return `${year}-${month}-${day}`;
  return now.toISOString().slice(0, 10);
}

/** True when a YYYY-MM-DD event date is today or earlier in Asia/Yerevan. */
export function isEventDateTodayOrPast(eventDate: string, now: Date = new Date()): boolean {
  if (!parseDateOnlyParts(eventDate)) return false;
  return eventDate.trim() <= yerevanTodayIso(now);
}

/** True when a YYYY-MM-DD event date is strictly before today in Asia/Yerevan. */
export function isEventDatePast(eventDate: string, now: Date = new Date()): boolean {
  if (!parseDateOnlyParts(eventDate)) return false;
  return eventDate.trim() < yerevanTodayIso(now);
}

function formatDateOnlyParts(parts: { year: number; month: number; day: number }, withYear: boolean): string {
  const label = `${parts.day} ${MONTHS_RU[parts.month - 1]}`;
  return withYear ? `${label} ${parts.year}` : label;
}

export type FeedDateInput = {
  date?: string | null;
  time?: string | null;
  endTime?: string | null;
  tentative?: boolean;
  fallback?: string;
};

/**
 * Public feed date line: title companion only.
 * Never substitutes updated_at / submitted_at / "today".
 * Date-only values keep calendar components — no device-TZ midnight conversion.
 */
export function formatFeedDateLine(options: FeedDateInput): string {
  const { date, time, endTime, tentative = false, fallback = "Дата уточняется" } = options;
  if (!date) return fallback;

  const parts = parseDateOnlyParts(date);
  let dayLabel: string;
  if (parts) {
    const withYear = parts.year !== currentYerevanYear();
    dayLabel = formatDateOnlyParts(parts, withYear);
  } else {
    const parsed = new Date(date);
    if (Number.isNaN(parsed.getTime())) return fallback;
    const yerevan = new Intl.DateTimeFormat("en-US", {
      timeZone: "Asia/Yerevan",
      year: "numeric",
      month: "numeric",
      day: "numeric",
    }).formatToParts(parsed);
    const year = Number(yerevan.find((part) => part.type === "year")?.value);
    const month = Number(yerevan.find((part) => part.type === "month")?.value);
    const day = Number(yerevan.find((part) => part.type === "day")?.value);
    if (!year || !month || !day) return fallback;
    dayLabel = formatDateOnlyParts({ year, month, day }, year !== currentYerevanYear());
  }

  if (time) {
    const timePart = endTime ? `${time}–${endTime}` : time;
    dayLabel = `${dayLabel} · ${timePart}`;
  }
  return tentative ? `Предварительно: ${dayLabel}` : dayLabel;
}

/** Project schedule helper — proposed fields are always tentative. */
export function formatProjectFeedDate(options: {
  proposedDate?: string | null;
  proposedTime?: string | null;
  dateIsTentative?: boolean | null;
}): string {
  if (!options.proposedDate) return "Дата уточняется";
  return formatFeedDateLine({
    date: options.proposedDate,
    time: options.proposedTime,
    tentative: options.dateIsTentative !== false,
  });
}
