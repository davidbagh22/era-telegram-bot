import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;
// Dedicated fixture with a real seeded points balance — the shared
// PARTICIPANT_TELEGRAM_ID (900001) must stay at exactly 0 points for
// admin_people.spec.ts's exact post-award balance assertion.
const AUCTION_BIDDER_TELEGRAM_ID = 900006;

test("admin creates a lot and the seeded bidder places a real bid on it", async ({ browser }) => {
  const adminContext = await browser.newContext();
  const adminPage = await adminContext.newPage();
  const participantContext = await browser.newContext();
  const participantPage = await participantContext.newPage();

  try {
    await adminPage.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
    await expect(adminPage.getByText("Управление")).toBeVisible();
    // Возможности now lives under the Работа group — see AdminScreen.tsx's
    // 2026-08 regrouping.
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

    // A real create through the full stack, verified by the lot appearing
    // in the admin's own list after the screen refetches it from the API.
    await expect(adminPage.getByText(lotTitle)).toBeVisible();

    await participantPage.goto(`/app/?devTelegramId=${AUCTION_BIDDER_TELEGRAM_ID}`);
    await participantPage.getByRole("button", { name: "Возможности" }).click();
    await participantPage.getByRole("button", { name: "Аукционы" }).click();

    // Hero card (2026-08 premium marketplace redesign): the card itself
    // shows title/countdown/current bid and a CTA that opens the actual
    // bid form in a detail bottom sheet, rather than an inline input.
    const lotCard = participantPage.locator(".era-card", { hasText: lotTitle });
    await expect(lotCard).toBeVisible();
    await lotCard.getByRole("button", { name: "Сделать ставку" }).click();

    const sheet = participantPage.getByRole("dialog", { name: lotTitle });
    await expect(sheet).toBeVisible();
    await sheet.getByPlaceholder(/^от /).fill("150");
    await sheet.getByRole("button", { name: "Подтвердить ставку" }).click();

    // A real bid through the full stack (API -> auction_service -> DB),
    // not a UI-only echo — verified by the sheet closing (immediate UI
    // update) and the bid showing up as "your bid" on the card itself
    // after the screen refetches the auction from the API.
    await expect(sheet).not.toBeVisible();
    await expect(lotCard.getByText("Ваша ставка: 150 баллов")).toBeVisible();
  } finally {
    await adminContext.close();
    await participantContext.close();
  }
});
