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
  await expect(page.getByRole("heading", { name: "Что происходит в ЭРА" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Разделы управления ЭРА" })).toBeVisible();
  await expect(page).toHaveURL(/#\/admin$/);
});

test("#/tasks deep link opens the standalone Tasks screen directly", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/tasks`);

  await expect(page.getByRole("heading", { name: "Задания" })).toBeVisible();
  await expect(page.getByText(/Пока нет задач в этом разделе/)).toBeVisible();
  await expect(page).toHaveURL(/#\/tasks$/);
});

test("#/events deep link opens the Events tab", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/events`);

  await expect(page.getByRole("heading", { name: "События" })).toBeVisible();
  await expect(page.getByText("E2E тестовое мероприятие")).toBeVisible();
});

test("#/opportunities deep link opens Opportunities on offers", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/opportunities`);

  await expect(page.getByRole("heading", { name: "Возможности" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Фильтры/ })).toBeVisible();
});

for (const hash of ["auctions", "rewards", "surveys"] as const) {
  test(`#/${hash} deep link keeps the legacy feature reachable`, async ({ page }) => {
    await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/${hash}`);
    await expect(page.getByRole("heading", { name: "Возможности" })).toBeVisible();
  });
}

test("legacy community deep link resolves to the simplified Opportunities surface", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}#/community`);
  await expect(page.getByRole("heading", { name: "Возможности" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Фильтры/ })).toBeVisible();
});
