import { expect, test } from "@playwright/test";

const PARTICIPANT_TELEGRAM_ID = 900001;

test("#/tasks deep link opens the legacy task surface directly", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/tasks`);

  await expect(page.getByRole("heading", { name: "Задачи" })).toBeVisible();
  await expect(page.getByText("Задач в этом разделе пока нет.")).toBeVisible();
});

test("#/events deep link opens the Events tab", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/events`);

  await expect(page.getByRole("heading", { name: "События" })).toBeVisible();
  await expect(page.getByText("E2E тестовое мероприятие")).toBeVisible();
});

test("#/opportunities deep link opens Community on offers", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/opportunities`);

  await expect(page.getByRole("heading", { name: "Предложения" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Фильтр" })).toBeVisible();
});

for (const [hash, heading] of [
  ["auctions", "Аукционы"],
  ["rewards", "Каталог"],
  ["surveys", "Опросы"],
] as const) {
  test(`#/${hash} deep link opens its Community feature`, async ({ page }) => {
    await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/${hash}`);
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
  });
}

test("community navigation stays synchronized with browser history", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/community`);
  await page.getByText("Аукционы", { exact: true }).first().click();
  await expect(page).toHaveURL(/#\/auctions$/);
  await expect(page.getByRole("heading", { name: "Аукционы" })).toBeVisible();

  await page.goBack();
  await expect(page).toHaveURL(/#\/community$/);
  await expect(page.getByRole("heading", { name: "Сообщество" })).toBeVisible();
});
