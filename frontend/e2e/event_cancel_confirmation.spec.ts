import { expect, test } from "@playwright/test";

const PARTICIPANT_TELEGRAM_ID = 900001;

test("cancelling a registration goes through a confirm sheet, not an immediate tap", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);
  await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "События" }).click();
  await expect(page.getByText("E2E тестовое мероприятие")).toBeVisible();

  await page.getByRole("button", { name: "Зарегистрироваться" }).click();
  const cancelTrigger = page.getByRole("button", { name: "Планы изменились" });
  await expect(cancelTrigger).toBeVisible();

  await cancelTrigger.click();
  await expect(page.getByText("Отменить регистрацию?")).toBeVisible();

  await page.getByRole("button", { name: "Не отменять" }).click();
  await expect(page.getByText("Отменить регистрацию?")).not.toBeVisible();
  await expect(cancelTrigger).toBeVisible();

  await cancelTrigger.click();
  await page.getByRole("button", { name: "Отменить регистрацию" }).click();

  await expect(page.getByRole("button", { name: "Зарегистрироваться" })).toBeVisible();
  await expect(page.getByText("Регистрация отменена")).toBeVisible();
});
