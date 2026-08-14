import { expect, test } from "@playwright/test";

const LEADER_TELEGRAM_ID = 900002;

test("leader opens the separate workspace and creates a new open task", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${LEADER_TELEGRAM_ID}`);

  await expect(page.getByRole("button", { name: "Профиль" })).toBeVisible();
  await page.getByRole("button", { name: "Профиль" }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();

  await expect(page.getByRole("heading", { name: "Пространство лидера" })).toBeVisible();

  await page.getByRole("button", { name: /Открытые задачи/ }).click();
  await expect(page.getByRole("heading", { name: "Открытые задачи" })).toBeVisible();
  await page.getByRole("button", { name: "Новая открытая задача" }).click();

  const taskTitle = `E2E задача ${Date.now()}`;
  await page.getByPlaceholder("Название").fill(taskTitle);
  await page.getByPlaceholder("Описание").fill("Создано E2E-тестом лидера.");
  const futureDeadline = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000)
    .toISOString()
    .slice(0, 16);
  await page.locator('input[type="datetime-local"]').fill(futureDeadline);

  await page.getByRole("button", { name: "Опубликовать" }).click();
  await expect(page.getByText(taskTitle)).toBeVisible();
});