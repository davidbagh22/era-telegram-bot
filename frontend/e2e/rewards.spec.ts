import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;
// Dedicated fixture with a real seeded points balance — redeeming and
// exchanging really does debit points (unlike placing an auction bid),
// so this can't reuse AUCTION_BIDDER_TELEGRAM_ID or the shared
// PARTICIPANT_TELEGRAM_ID (900001, which admin_people.spec.ts needs at
// exactly 0 points).
const REWARD_REDEEMER_TELEGRAM_ID = 900007;

test("admin publishes a reward, the seeded participant redeems it, and the admin answers and exchanges it", async ({
  browser,
}) => {
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
    await adminPage.getByRole("button", { name: "Каталог" }).click();

    const rewardName = `E2E Reward ${Date.now()}`;
    await adminPage.getByPlaceholder("Название").fill(rewardName);
    await adminPage.getByPlaceholder("Что получит участник").fill("Создано E2E-тестом.");
    await adminPage.getByPlaceholder("Стоимость в баллах").fill("50");
    await adminPage.getByRole("button", { name: "Опубликовать в каталоге" }).click();

    // A real create through the full stack, verified by the reward
    // appearing in the admin's own catalog list after the refetch.
    const rewardCard = adminPage.locator(".era-card", { hasText: rewardName });
    await expect(rewardCard).toBeVisible();

    await participantPage.goto(`/app/?devTelegramId=${REWARD_REDEEMER_TELEGRAM_ID}`);
    await participantPage
      .getByRole("navigation", { name: "Основная навигация" })
      .getByRole("button", { name: "Сообщество" })
      .click();
    await participantPage.getByRole("button", { name: "Каталог" }).click();

    const participantCard = participantPage.locator(".era-card", { hasText: rewardName });
    await expect(participantCard).toBeVisible();
    await participantCard.getByRole("button", { name: /^Обменять/ }).click();

    // A real redemption request through the full stack, verified by the
    // reward now showing a status badge instead of the redeem button.
    await expect(participantCard.getByText("заявка отправлена")).toBeVisible();

    await adminPage.reload();
    await adminPage.getByRole("button", { name: "Работа" }).click();
    await adminPage.getByRole("button", { name: "Возможности" }).click();
    await adminPage.getByRole("button", { name: "Каталог" }).click();
    const redemptionCard = adminPage.locator(".era-card", { hasText: "E2E Reward Redeemer" });
    await expect(redemptionCard).toBeVisible();
    await redemptionCard.getByPlaceholder("Ответ участнику").fill("Свяжемся с Вами по почте.");
    await redemptionCard.getByRole("button", { name: "Отправить ответ" }).click();
    await expect(redemptionCard.getByText("ответ отправлен")).toBeVisible();
    await redemptionCard.getByRole("button", { name: "Обменять и списать баллы" }).click();

    // A real exchange through the full stack (API -> redemption_service ->
    // points_service), verified by the redemption disappearing from the
    // open-redemptions list once its status moves past "answered".
    await expect(redemptionCard).toHaveCount(0);
  } finally {
    await adminContext.close();
    await participantContext.close();
  }
});
