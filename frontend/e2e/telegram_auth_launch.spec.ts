import { createHmac } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";

async function telegramBridge(page: Page, initData: string) {
  await page.route("https://telegram.org/js/telegram-web-app.js", (route) => route.fulfill({
    contentType: "application/javascript",
    body: "/* Bridge supplied by the test's Telegram client. */",
  }));
  await page.addInitScript((data) => {
    const calls: string[] = [];
    Object.assign(window, {
      telegramLoginCalls: calls,
      Telegram: { WebApp: {
        initData: data,
        ready() {}, expand() {}, onEvent() {},
        openTelegramLink(url: string) { calls.push(url); },
        close() { calls.push("close"); },
      } },
    });
  }, initData);
}

test("old simple-mode launch offers bot login without retrying empty credentials", async ({ page }) => {
  await telegramBridge(page, "");
  const authRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/miniapp/auth")) authRequests.push(request.url());
  });
  await page.goto("/app/");
  await expect(page.getByRole("heading", { name: "Войдите через бота ЭРА" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Обновить", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Войти через бота", exact: true }).click();
  expect(await page.evaluate(() => (window as unknown as { telegramLoginCalls: string[] }).telegramLoginCalls))
    .toEqual(["https://t.me/ERA_1bot?start=miniapp", "close"]);
  expect(authRequests).toEqual([]);
});

test("signed Telegram launch logs into the real API without dev authentication", async ({ page }) => {
  const fields = {
    auth_date: String(Math.floor(Date.now() / 1000)),
    query_id: "test-inline-launch",
    user: JSON.stringify({ id: 900001, first_name: "Participant" }),
  };
  const checkString = Object.entries(fields).sort().map(([key, value]) => `${key}=${value}`).join("\n");
  const key = createHmac("sha256", "WebAppData").update(process.env.BOT_TOKEN ?? "0000000000:E2ETESTTOKEN").digest();
  const hash = createHmac("sha256", key).update(checkString).digest("hex");
  const initData = new URLSearchParams({ ...fields, hash }).toString();
  await telegramBridge(page, initData);
  const authResponse = page.waitForResponse((response) => response.url().endsWith("/miniapp/auth"));
  await page.goto("/app/?eraPath=events");
  const response = await authResponse;
  expect(response.status()).toBe(200);
  expect(response.request().postDataJSON()).toEqual({ initData });
  expect((await response.json()).user.telegram_id).toBe(900001);
  await expect(page.getByRole("heading", { name: "Войдите через бота ЭРА" })).toHaveCount(0);
  await expect(page).toHaveURL(/#\/events$/);
});
