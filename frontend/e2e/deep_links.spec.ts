import { expect, test } from "@playwright/test";

const PARTICIPANT_TELEGRAM_ID = 900001;
const ADMIN_TELEGRAM_ID = 900003;

test("eraPath query opens Projects when Telegram provides no fragment", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}&eraPath=projects`);

  await expect(page.getByRole("heading", { name: "Проекты" })).toBeVisible();
  await expect(page.getByText("Начните с одной мысли")).toBeVisible();
});

test("fresh Telegram eraPath overrides a stale cached hash", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}&eraPath=projects#/events`);

  await expect(page.getByRole("heading", { name: "Проекты" })).toBeVisible();
  await expect(page).toHaveURL(/#\/projects$/);
  await expect(page).not.toHaveURL(/eraPath=/);
});

test("eraPath admin opens the separate Admin workspace directly", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}&eraPath=admin`);

  await expect(page.getByText("Управление", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Пульт управления" })).toBeVisible();
});

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
