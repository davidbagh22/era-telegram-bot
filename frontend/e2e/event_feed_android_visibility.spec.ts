import { expect, test } from "@playwright/test";

// Reproduces the Android evidence: users mistake the old "Для меня" alias
// for a filtered list and do not discover the rest of the vertical feed.
test("Android event feed has honest filter, visible continuation and usable cards", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 760 });
  const events = Array.from({ length: 5 }, (_, index) => ({
    id: 100 + index,
    title: index === 0 ? "Географический диктант — 2026" : `Культурное мероприятие ЭРА номер ${index}`,
    event_date: `2026-11-${String(22 + index).padStart(2, "0")}`,
    event_time: "12:00",
    end_time: null,
    status: "registration_open",
  }));
  await page.route(url => url.pathname === "/api/v1/events" && url.searchParams.has("scope"),
    async route => route.fulfill({ json: events }));
  await page.goto("/app/?devTelegramId=900001#/events");
  await expect(page.getByRole("heading", { name: "Афиша", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Фильтр афиши" })).toContainText("Все события");
  await expect(page.getByText("↓ Листайте ниже · 5 мероприятий")).toBeVisible();
  const cards = page.locator(".era-events-feed .era-typography-feed-card");
  await expect(cards).toHaveCount(5);
  const first = await cards.first().boundingBox();
  expect(first).not.toBeNull();
  expect(first!.width).toBeLessThanOrEqual(321);
  const last = cards.last();
  await last.scrollIntoViewIfNeeded();
  await expect(last).toBeVisible();
  await page.getByRole("button", { name: "Фильтр афиши" }).click();
  await expect(page.getByRole("heading", { name: "Какие события показать?" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Все события/ })).toBeVisible();
  await expect(page.getByText("Для меня", { exact: true })).toHaveCount(0);
});
