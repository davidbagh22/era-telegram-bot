import { expect, test } from "@playwright/test";

const PARTICIPANT_TELEGRAM_ID = 900001;

test("cancelling a registration goes through a confirm sheet, not an immediate tap", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);
  await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "События" }).click();
  await expect(page.getByText("E2E тестовое мероприятие")).toBeVisible();
  await page.getByRole("button", { name: "Открыть событие" }).first().click();

  await page.getByRole("button", { name: "Участвовать" }).click();
  await expect(page.getByRole("heading", { name: "Место за вами" })).toBeVisible();
  await page.getByRole("button", { name: "Готово" }).click();

  const cancelTrigger = page.getByRole("button", { name: "Отказаться", exact: true });
  await expect(cancelTrigger).toBeVisible();

  await cancelTrigger.click();
  await expect(page.getByText("Отказаться от участия?")).toBeVisible();

  await page.getByRole("button", { name: "Остаться" }).click();
  await expect(page.getByText("Отказаться от участия?")).not.toBeVisible();
  await expect(cancelTrigger).toBeVisible();

  await cancelTrigger.click();
  await page.getByRole("button", { name: "Отказаться", exact: true }).last().click();

  await expect(page.getByRole("button", { name: "Участвовать" })).toBeVisible();
  await expect(page.getByText("Участие отменено")).toBeVisible();
});
