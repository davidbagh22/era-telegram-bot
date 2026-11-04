import { expect, test, type Page } from "@playwright/test";

// The API response is altered only inside the isolated Playwright browser.
// No production events, registrations, points or Telegram messages are touched.
const PARTICIPANT_TELEGRAM_ID = 900001;

async function openEventWithLinks(page: Page, chatUrl: string, submitUrl: string) {
  // Opening a card changes the hash and remounts EventsTab with scope=all.
  // Preserve the same isolated override across both list and detail requests.
  let targetId: number | null = null;
  await page.route("**/api/v1/events?scope=*", async (route) => {
    const response = await route.fetch();
    const events = (await response.json()) as Array<Record<string, unknown>>;
    if (targetId === null && events.length > 0) {
      targetId = Number(events[0].id);
    }
    const updated = events.map((event) => event.id === targetId
      ? { ...event, chat_url: chatUrl, registration_status: "registered" }
      : event);
    await route.fulfill({ response, json: updated });
  });

  await page.route("**/api/v1/events/*/activities", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{
        id: 987654,
        title: "E2E проверка ссылки",
        description: "Изолированный ответ API",
        submission_type: "text",
        points: 0,
        my_status: null,
        submit_deep_link: submitUrl,
      }]),
    });
  });

  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/events`);
  await expect(page.getByRole("button", { name: "Открыть событие" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Открыть событие" }).first().click();
  await expect(page.getByText("E2E проверка ссылки")).toBeVisible();
}

test("event chat and activity proof links reject unsafe URL schemes", async ({ page }) => {
  await openEventWithLinks(page, "javascript:alert(1)", "data:text/html,<script>alert(1)</script>");
  await expect(page.getByRole("link", { name: "Открыть чат" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Отправить результат" })).toHaveCount(0);
});

test("event chat and activity proof links preserve valid Telegram HTTPS URLs", async ({ page }) => {
  const chat = "https://t.me/era_leaders1";
  const proof = "https://t.me/ERA_1bot?start=activity_submit_987654";
  await openEventWithLinks(page, chat, proof);
  await expect(page.getByRole("link", { name: "Открыть чат" })).toHaveAttribute("href", chat);
  await expect(page.getByRole("link", { name: "Отправить результат" })).toHaveAttribute("href", proof);
});
