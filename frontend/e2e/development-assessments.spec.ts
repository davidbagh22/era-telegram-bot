import { expect, test } from "@playwright/test";

const PARTICIPANT_TELEGRAM_ID = 900001;

test("participant completes WHO-5 through My Vector and sees the saved result", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${PARTICIPANT_TELEGRAM_ID}`);

  const vectorEntry = page.getByRole("button", { name: "Открыть мой вектор", exact: true });
  await expect(vectorEntry).toBeVisible();
  await vectorEntry.click();

  const consentButton = page.getByRole("button", { name: "Понятно, продолжить" });
  if (await consentButton.isVisible().catch(() => false)) await consentButton.click();

  await expect(page.getByRole("heading", { name: "Мой вектор" })).toBeVisible();
  await page.getByRole("button", { name: /Исследования/ }).click();
  await expect(page.getByRole("heading", { name: "Все исследования" })).toBeVisible();

  await page.getByRole("button", { name: /Как мне сейчас\?/ }).click();
  await expect(page.getByRole("heading", { name: "Как мне сейчас?" })).toBeVisible();
  await page.getByRole("button", { name: "Начать" }).click();

  for (let index = 0; index < 5; index += 1) {
    await expect(page.getByRole("button", { name: "Всё время" })).toBeVisible();
    await page.getByRole("button", { name: "Всё время" }).click();
  }

  await expect(page.getByText("ГОТОВО К РЕЗУЛЬТАТУ")).toBeVisible();
  await page.getByRole("button", { name: "Получить результат" }).click();
  await expect(page.getByText("ТВОЙ РЕЗУЛЬТАТ")).toBeVisible();
  await expect(page.getByText(/100 из 100/)).toBeVisible();
});
