import { expect, test } from "@playwright/test";

test("certificate holder downloads their issued PDF from portfolio", async ({ page }) => {
  await page.goto("/app/?devTelegramId=900011");
  await page.getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Моё портфолио/ }).click();
  const section = page.getByRole("region", { name: "Сертификаты ЭРА" });
  await expect(section).toContainText("E2E Подтверждённое участие");
  const download = page.waitForEvent("download");
  await section.getByRole("button", { name: /E2E Подтверждённое участие/ }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/^ERA-CERT-\d+\.pdf$/);
});

test("event calendar download uses UTC rather than the device timezone", async ({ page, request }) => {
  const auth = await request.post("/api/v1/miniapp/auth", { data: { initData: "", devTelegramId: 900001 } });
  expect(auth.ok()).toBeTruthy();
  const { token } = await auth.json();
  const response = await request.get("/api/v1/events", { headers: { Authorization: `Bearer ${token}` } });
  const events = await response.json();
  const event = events.find((e: { title: string }) => e.title === "E2E тестовое мероприятие");
  expect(event).toBeTruthy();
  await page.goto("/app/?devTelegramId=900001#/events");
  const card = page.locator(".era-card", { hasText: event.title }).first();
  await card.getByRole("button", { name: "Открыть событие" }).click();
  // The UI now offers explicit Google and .ics paths; desktop keeps file download.
  const google = page.getByRole("link", { name: "Google Календарь" });
  await expect(google).toBeVisible();
  const googleUrl = new URL((await google.getAttribute("href"))!);
  expect(googleUrl.searchParams.get("ctz")).toBe("Asia/Yerevan");
  expect(googleUrl.searchParams.get("dates")).toMatch(/^\\d{8}T\\d{6}Z\\/\\d{8}T\\d{6}Z$/);
  const calendar = page.getByRole("button", { name: "Календарь Apple (.ics)" });
  const download = page.waitForEvent("download");
  await calendar.click();
  expect((await download).suggestedFilename()).toBe(`ERA-${event.id}.ics`);
  const ics = await request.get(`/api/v1/events/${event.id}/calendar.ics`, { headers: { Authorization: `Bearer ${token}` } });
  expect(ics.ok()).toBeTruthy();
  expect(await ics.text()).toMatch(/DTSTART:\d{8}T\d{6}Z/);
});

test("ranking has an explicit seasonal period without replacing the total", async ({ page }) => {
  await page.goto("/app/?devTelegramId=900011#/leaderboard");
  await expect(page.getByRole("heading", { name: "Рейтинг участников" })).toBeVisible();
  const period = page.getByRole("combobox");
  await expect(period).toContainText("E2E Сезон");
  await period.selectOption({ label: "E2E Сезон" });
  await expect(page.getByText(/Позднее подтверждение относится/)).toBeVisible();
  await period.selectOption({ label: "За всё время" });
  await expect(page.getByRole("heading", { name: "Топ участников" })).toBeVisible();
});
