import { expect, test } from "@playwright/test";

const PARTICIPANT_TELEGRAM_ID = 900001;

test("participant can open professional portfolio and CV tools", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);
  await page.getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Моё портфолио/ }).click();

  await expect(page.getByRole("heading", { name: "Моё портфолио" })).toBeVisible();
  await expect(page.getByText("Всё, что ты сделал. Всё, что можешь показать.")).toBeVisible();
  await expect(page.getByRole("button", { name: "＋ Добавить результат" })).toBeVisible();
  await expect(page.getByText("Рекомендация ЭРА", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Собрать резюме PDF" })).toBeVisible();
  await expect(page.getByText(/Моего вектора/)).toBeVisible();
});
