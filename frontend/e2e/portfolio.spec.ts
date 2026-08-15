import { expect, test } from "@playwright/test";

const PARTICIPANT_TELEGRAM_ID = 900001;

test("participant's earned badge appears in the linked ERA portfolio", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);

  await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "Профиль", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Профиль" })).toBeVisible();
  await expect(page.getByText("Цифровое портфолио ЭРА")).toBeVisible();

  await page.getByRole("button", { name: /Достижения/ }).first().click();
  await expect(page.getByRole("heading", { name: "Достижения" })).toBeVisible();
  await expect(page.getByText("E2E Тестовый значок")).toBeVisible();
});
