import { expect, test, type Page } from "@playwright/test";

// All events and calendar files in this spec are isolated E2E fixture responses.
// No real event, registration, balance, or Telegram message is created.
async function openCalendarChoices(page: Page) {
  let chosenId: number | null = null;
  await page.route("**/api/v1/events?scope=*", async (route) => {
    const response = await route.fetch();
    const items = (await response.json()) as Array<Record<string, unknown>>;
    if (chosenId === null && items.length > 0) chosenId = Number(items[0].id);
    await route.fulfill({
      response,
      json: items.map((item) => item.id === chosenId ? {
        ...item,
        title: "Встреча ЭРА 🇦🇲",
        description: "Обсуждение в Ереване 🎓",
        full_description: "Программа на русском и հայերեն 🎓",
        event_date: "2026-11-03",
        event_time: "18:00",
        end_time: "19:30",
        location: "Ереван",
        address: "ул. Тест, 1",
      } : item),
    });
  });
  await page.goto("/app/?devTelegramId=900001#/events");
  await expect(page.getByRole("button", { name: "Открыть событие" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Открыть событие" }).first().click();
  await expect(page.getByRole("link", { name: "Google Календарь" })).toBeVisible();
}

test("Google Calendar uses correct Yerevan UTC times and Unicode without opening ICS", async ({ page }) => {
  await openCalendarChoices(page);
  const href = await page.getByRole("link", { name: "Google Календарь" }).getAttribute("href");
  expect(href).not.toBeNull();
  const url = new URL(href!);
  expect(url.origin).toBe("https://calendar.google.com");
  expect(url.searchParams.get("action")).toBe("TEMPLATE");
  expect(url.searchParams.get("dates")).toBe("20261103T140000Z/20261103T153000Z");
  expect(url.searchParams.get("ctz")).toBe("Asia/Yerevan");
  expect(url.searchParams.get("text")).toBe("Встреча ЭРА 🇦🇲");
  expect(url.searchParams.get("details")).toContain("հայերեն 🎓");
  expect(url.searchParams.get("location")).toBe("Ереван, ул. Тест, 1");
});

test("iPhone without file sharing never opens a raw ICS blob in Telegram", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "userAgent", {
      configurable: true, get: () => "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Telegram-iOS",
    });
    Object.defineProperty(navigator, "canShare", { configurable: true, value: undefined });
    Object.defineProperty(navigator, "share", { configurable: true, value: undefined });
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true, value: () => { throw new Error("raw blob preview must not run on iPhone"); },
    });
  });
  await page.route("**/api/v1/events/*/calendar.ics", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/calendar; charset=utf-8",
      body: "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n",
    });
  });
  await openCalendarChoices(page);
  await page.getByRole("button", { name: "Календарь Apple (.ics)" }).click();
  await expect(page.getByText(/Telegram на iPhone не поддерживает передачу/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Google Календарь" })).toBeVisible();
});

test("supported iOS Web Share receives a UTF-8 .ics File instead of a blob URL", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "userAgent", {
      configurable: true, get: () => "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)",
    });
    Object.defineProperty(navigator, "canShare", { configurable: true, value: () => true });
    Object.defineProperty(navigator, "share", {
      configurable: true,
      value: async (data: ShareData) => {
        (window as typeof window & { __eraSharedFile?: string }).__eraSharedFile = data.files?.[0]?.name;
      },
    });
  });
  await page.route("**/api/v1/events/*/calendar.ics", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/calendar; charset=utf-8",
      body: "BEGIN:VCALENDAR\r\nSUMMARY:Встреча ЭРА 🇦🇲\r\nEND:VCALENDAR\r\n",
    });
  });
  await openCalendarChoices(page);
  await page.getByRole("button", { name: "Календарь Apple (.ics)" }).click();
  await expect.poll(() => page.evaluate(() =>
    (window as typeof window & { __eraSharedFile?: string }).__eraSharedFile ?? null,
  )).toMatch(/^ERA-\d+\.ics$/);
});
