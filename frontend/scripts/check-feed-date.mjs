/**
 * Regression for date-only feed formatting: must not shift calendar day
 * when the process TZ is ahead of Asia/Yerevan (e.g. Asia/Tokyo).
 *
 * Mirrors frontend/src/utils/feedDate.ts date-only path.
 */
const MONTHS_RU = [
  "января", "февраля", "марта", "апреля", "мая", "июня",
  "июля", "августа", "сентября", "октября", "ноября", "декабря",
];

function parseDateOnlyParts(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
  if (!match) return null;
  return { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) };
}

function currentYerevanYear() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Yerevan",
    year: "numeric",
  }).formatToParts(new Date());
  return Number(parts.find((part) => part.type === "year")?.value);
}

function formatFeedDateLine({ date, time, endTime, fallback = "Дата уточняется" }) {
  if (!date) return fallback;
  const parts = parseDateOnlyParts(date);
  if (!parts) return fallback;
  const withYear = parts.year !== currentYerevanYear();
  let dayLabel = `${parts.day} ${MONTHS_RU[parts.month - 1]}`;
  if (withYear) dayLabel = `${dayLabel} ${parts.year}`;
  if (!time) return dayLabel;
  return `${dayLabel} · ${endTime ? `${time}–${endTime}` : time}`;
}

function assertEqual(actual, expected, label) {
  if (actual !== expected) {
    console.error(`FAIL ${label}: got ${JSON.stringify(actual)}, expected ${JSON.stringify(expected)}`);
    process.exitCode = 1;
  } else {
    console.log(`ok ${label}`);
  }
}

// Broken path (old): local midnight + timeZone Yerevan under Tokyo shifts day.
function brokenFormat(date, time) {
  const [y, m, d] = date.split("-").map(Number);
  const local = new Date(y, m - 1, d);
  const dayLabel = local.toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    timeZone: "Asia/Yerevan",
  });
  return `${dayLabel} · ${time}`;
}

const sample = { date: "2026-12-12", time: "17:30" };
const fixed = formatFeedDateLine(sample);
assertEqual(fixed, "12 декабря · 17:30", "date-only stays on 12 Dec");

if (process.env.TZ === "Asia/Tokyo" || process.env.FORCE_TZ_CHECK === "1") {
  const broken = brokenFormat(sample.date, sample.time);
  if (broken.startsWith("12 декабря")) {
    console.log("note: process TZ did not reproduce the Tokyo shift in this environment");
  } else {
    console.log(`confirmed broken baseline under TZ=${process.env.TZ}: ${broken}`);
  }
  if (fixed.startsWith("11 декабря")) {
    console.error("FAIL fixed formatter still shifted under Tokyo");
    process.exitCode = 1;
  }
}

if (!process.exitCode) console.log("feedDate checks passed");
