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
