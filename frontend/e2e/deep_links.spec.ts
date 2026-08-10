import { expect, test } from "@playwright/test";

// PR 36 (Bot/Mini App role split): the bot's "📅 Ближайшее"/"✅ Мои
// задачи"/"⭐ Возможности" quick-access buttons deep-link straight into
// `${miniapp_url}/#/<path>` (app/utils/deep_links.py's miniapp_events_url /
// miniapp_tasks_url / miniapp_opportunities_url) instead of opening the
// Mini App at Home and making the user navigate themselves. These specs
// verify frontend/src/app/App.tsx's parseDeepLink() actually lands on the
// right screen for each of those three targets.

const PARTICIPANT_TELEGRAM_ID = 900001;

test("#/tasks deep link opens Activity on the Tasks tab", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/tasks`);

  await expect(page.getByRole("heading", { name: "Активность" })).toBeVisible();
  // No Task rows exist anywhere in the e2e seed data, so this empty state
  // is deterministic — its presence (not the generic "Активность" heading,
  // which renders for any section) is what proves the Tasks tab, not the
  // "events" default, actually landed.
  await expect(page.getByText("Задач в этом разделе пока нет.")).toBeVisible();
});

test("#/events deep link opens Activity on the Events tab", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/events`);

  await expect(page.getByRole("heading", { name: "Активность" })).toBeVisible();
  await expect(page.getByText("E2E тестовое мероприятие")).toBeVisible();
});

test("#/opportunities deep link opens the Opportunities screen", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/opportunities`);

  await expect(page.getByRole("button", { name: "Для тебя" })).toBeVisible();
});
