import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;
const AUCTION_BIDDER_TELEGRAM_ID = 900006;

async function enterAdminWorkspace(page: import("@playwright/test").Page) {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
  await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await expect(page.getByText("Управление", { exact: true })).toBeVisible();
}

test("admin creates a lot and the seeded bidder places a real bid on it", async ({ browser }) => {
  const adminContext = await browser.newContext();
  const adminPage = await adminContext.newPage();
  const participantContext = await browser.newContext();
  const participantPage = await participantContext.newPage();

  try {
    await enterAdminWorkspace(adminPage);
    await adminPage.getByRole("button", { name: "Работа" }).click();
    await adminPage.getByRole("button", { name: "Возможности" }).click();
    await adminPage.getByRole("button", { name: "Аукционы" }).click();

    const lotTitle = `E2E Lot ${Date.now()}`;
    await adminPage.getByPlaceholder("Название").fill(lotTitle);
    await adminPage.getByPlaceholder("Описание").fill("Создано E2E-тестом.");
    await adminPage.getByPlaceholder("Стартовая ставка").fill("100");
    await adminPage.getByPlaceholder("Шаг ставки").fill("10");
    const future = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 16);
    await adminPage.locator('input[type="datetime-local"]').fill(future);
    await adminPage.getByRole("button", { name: "Опубликовать лот" }).click();
    await expect(adminPage.getByText(lotTitle)).toBeVisible();

    await participantPage.goto(`/app/?devTelegramId=${AUCTION_BIDDER_TELEGRAM_ID}`);
    await participantPage.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "Сообщество" }).click();
    await participantPage.getByRole("button", { name: "Аукционы" }).click();
    const lotCard = participantPage.locator(".era-card", { hasText: lotTitle });
    await expect(lotCard).toBeVisible();
    await lotCard.getByRole("button", { name: "Сделать ставку" }).click();

    const sheet = participantPage.getByRole("dialog", { name: lotTitle });
    await expect(sheet).toBeVisible();
    await sheet.getByPlaceholder(/^от /).fill("150");
    await sheet.getByRole("button", { name: "Подтвердить ставку" }).click();
    await expect(sheet).not.toBeVisible();
    await expect(lotCard.getByText("Ваша ставка: 150 баллов")).toBeVisible();
  } finally {
    await adminContext.close();
    await participantContext.close();
  }
});