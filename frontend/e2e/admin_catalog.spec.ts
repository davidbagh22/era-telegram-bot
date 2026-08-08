import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;

test("admin creates a partner and an offer for it through the real API", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
  await expect(page.getByText("ЭРА / ADMIN")).toBeVisible();

  await page.getByRole("button", { name: "Возможности" }).click();
  await page.getByRole("button", { name: "Партнёры" }).click();

  const partnerName = `E2E Partner ${Date.now()}`;
  await page.getByPlaceholder("Название").fill(partnerName);
  await page.getByPlaceholder("Описание").fill("Создано E2E-тестом.");
  await page.getByRole("button", { name: "Добавить партнёра" }).click();

  // A real create through the full stack, verified by the partner
  // appearing in the list after the screen refetches it from the API.
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
