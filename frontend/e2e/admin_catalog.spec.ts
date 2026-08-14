import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;

async function enterAdminWorkspace(page: import("@playwright/test").Page) {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
  await page.getByRole("button", { name: "Профиль" }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await expect(page.getByText("Управление", { exact: true })).toBeVisible();
}

test("admin creates a partner and an offer for it through the real API", async ({ page }) => {
  await enterAdminWorkspace(page);

  await page.getByRole("button", { name: "Работа" }).click();
  await page.getByRole("button", { name: "Возможности" }).click();
  await page.getByRole("button", { name: "Партнёры" }).click();

  const partnerName = `E2E Partner ${Date.now()}`;
  await page.getByPlaceholder("Название").fill(partnerName);
  await page.getByPlaceholder("Описание").fill("Создано E2E-тестом.");
  await page.getByRole("button", { name: "Добавить партнёра" }).click();

  await expect(page.getByText(partnerName)).toBeVisible();

  await page.getByRole("button", { name: "Предложения" }).click();
  await page.locator("select").selectOption({ label: partnerName });

  const offerTitle = `E2E Offer ${Date.now()}`;
  await page.getByPlaceholder("Название").fill(offerTitle);
  await page.getByPlaceholder("Описание").fill("Создано E2E-тестом.");
  await page.getByPlaceholder("Стоимость в баллах").fill("25");
  await page.getByRole("button", { name: "Добавить предложение" }).click();

  await expect(page.getByText(offerTitle)).toBeVisible();
  await expect(page.getByText(`${partnerName} · 25 баллов`)).toBeVisible();
});