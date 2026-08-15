import { expect, test } from "@playwright/test";

const PARTICIPANT_TELEGRAM_ID = 900001;

test("participant logs in, sees Home, opens event details, and registers", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);

  await expect(page.getByText("ERA SCORE", { exact: true })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Основная навигация" })).toBeVisible();

  await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "События" }).click();
  await expect(page.getByRole("heading", { name: "События" })).toBeVisible();

  await expect(page.getByText("E2E тестовое мероприятие")).toBeVisible();
  await page.getByRole("button", { name: /E2E тестовое мероприятие\. Открыть событие/ }).first().click();

  await expect(page.getByRole("heading", { name: "E2E тестовое мероприятие" })).toBeVisible();
  await page.getByRole("button", { name: "Участвовать", exact: true }).click();

  await expect(page.getByText("Место за вами")).toBeVisible();
  await expect(page.getByText("Вы участвуете", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Отказаться от участия" })).toBeVisible();
});
