const YEREVAN = "Asia/Yerevan";

/** Parse date-only YYYY-MM-DD without UTC day-shift. */
export function parseDateOnly(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (!year || month < 1 || month > 12 || day < 1 || day > 31) return null;
  return new Date(year, month - 1, day);
}

function formatDayMonth(date: Date, withYear: boolean): string {
  const opts: Intl.DateTimeFormatOptions = {
    day: "numeric",
    month: "long",
    timeZone: YEREVAN,
  };
  if (withYear) opts.year = "numeric";
  return date.toLocaleDateString("ru-RU", opts);
}

/**
 * Public feed date line: title companion only.
 * Never substitutes updated_at / submitted_at / "today".
 */
export function formatFeedDateLine(options: {
  date?: string | null;
  time?: string | null;
  endTime?: string | null;
  fallback?: string;
}): string {
  const { date, time, endTime, fallback = "Дата уточняется" } = options;
  if (!date) return fallback;

  const dateOnly = parseDateOnly(date);
  let dayLabel: string;
  if (dateOnly) {
    const now = new Date();
    const withYear = dateOnly.getFullYear() !== now.getFullYear();
    dayLabel = formatDayMonth(dateOnly, withYear);
  } else {
    const parsed = new Date(date);
    if (Number.isNaN(parsed.getTime())) return fallback;
    const withYear = parsed.getFullYear() !== new Date().getFullYear();
    dayLabel = formatDayMonth(parsed, withYear);
  }

  if (!time) return dayLabel;
  const timePart = endTime ? `${time}–${endTime}` : time;
  return `${dayLabel} · ${timePart}`;
}
