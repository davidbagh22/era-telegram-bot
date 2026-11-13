import { expect, test } from "@playwright/test";

test("anniversary card hands off to guest RSVP without member registration POST", async ({ page }) => {
  await page.context().route("https://t.me/ERA_1bot?start=anniversary2026", route => route.fulfill({ status: 200, body: "Guest RSVP" }));
  let memberPosts = 0;
  page.on("request", request => {
    if (request.method() === "POST" && /\/events\/\d+\/register/.test(request.url())) memberPosts++;
  });
  await page.route("**/api/v1/events?scope=*", async route => {
    const response = await route.fetch();
    const events = await response.json();
    await route.fulfill({ response, json: events.map((event: Record<string, unknown>) => ({
      ...event, registration_status: null, can_register: false,
      registration_url: "https://t.me/ERA_1bot?start=anniversary2026",
    })) });
  });
  await page.goto("/app/?devTelegramId=900001#/events");
  await page.getByRole("button", { name: "Открыть событие" }).first().click();
  const cta = page.getByRole("button", { name: "Зарегистрироваться", exact: true });
  await expect(cta).toBeVisible();
  await page.evaluate(() => {
    const calls: string[] = [];
    (window as unknown as { guestLinks: string[] }).guestLinks = calls;
    window.Telegram = window.Telegram || {};
    window.Telegram.WebApp = window.Telegram.WebApp || {} as NonNullable<typeof window.Telegram.WebApp>;
    window.Telegram.WebApp.openTelegramLink = (url: string) => { calls.push(url); };
  });
  await cta.click();
  expect(await page.evaluate(() => (window as unknown as { guestLinks: string[] }).guestLinks))
    .toEqual(["https://t.me/ERA_1bot?start=anniversary2026"]);
  expect(memberPosts).toBe(0);
});
