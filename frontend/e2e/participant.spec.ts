import { expect, test } from "@playwright/test";

const PARTICIPANT_TELEGRAM_ID = 900001;

test("participant gets dark ERA UI, opens event details, and registers", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);

  await expect(page.getByText("ERA SCORE")).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const bodyBackground = await page.locator("body").evaluate((node) => getComputedStyle(node).backgroundColor);
  expect(bodyBackground).not.toBe("rgb(255, 255, 255)");

  await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "События" }).click();
  await expect(page.getByRole("heading", { name: "События" })).toBeVisible();

  const eventCard = page.getByText("E2E тестовое мероприятие");
  await expect(eventCard).toBeVisible();
  await page.getByRole("button", { name: "Открыть событие" }).first().click();

  await expect(page.getByRole("heading", { name: "E2E тестовое мероприятие" })).toBeVisible();
  await page.getByRole("button", { name: "Участвовать" }).click();

  await expect(page.getByRole("heading", { name: "Место за вами" })).toBeVisible();
  await expect(page.getByText("✓ Вы участвуете").first()).toBeVisible();
  await page.getByRole("button", { name: "Готово" }).click();
  await expect(page.getByRole("button", { name: "Отказаться" })).toBeVisible();
});
