import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;
const REWARD_REDEEMER_TELEGRAM_ID = 900007;

async function enterAdminWorkspace(page: import("@playwright/test").Page) {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
  await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await expect(page.getByText("Управление", { exact: true })).toBeVisible();
}

test("admin publishes a reward, the seeded participant redeems it, and the admin answers and exchanges it", async ({ browser }) => {
  const adminContext = await browser.newContext();
  const adminPage = await adminContext.newPage();
  const participantContext = await browser.newContext();
  const participantPage = await participantContext.newPage();

  try {
    await enterAdminWorkspace(adminPage);
    await adminPage.getByRole("button", { name: "Работа" }).click();
    await adminPage.getByRole("button", { name: "Возможности" }).click();
    await adminPage.getByRole("button", { name: "Каталог" }).click();

    const rewardName = `E2E Reward ${Date.now()}`;
    await adminPage.getByPlaceholder("Название").fill(rewardName);
    await adminPage.getByPlaceholder("Что получит участник").fill("Создано E2E-тестом.");
    await adminPage.getByPlaceholder("Стоимость в баллах").fill("50");
    await adminPage.getByRole("button", { name: "Опубликовать в каталоге" }).click();
    await expect(adminPage.locator(".era-card", { hasText: rewardName })).toBeVisible();

    // Rewards are legacy-routable but intentionally no longer a primary
    // Community nav item (see CommunityScreen.tsx) -- reach it the way a
    // real notification/deep link would.
    await participantPage.goto(`/app/?devTelegramId=${REWARD_REDEEMER_TELEGRAM_ID}#/rewards`);
    const participantCard = participantPage.locator(".era-card", { hasText: rewardName });
    await expect(participantCard).toBeVisible();
    await participantCard.getByRole("button", { name: /^Обменять/ }).click();
    await expect(participantCard.getByText("заявка отправлена")).toBeVisible();

    await enterAdminWorkspace(adminPage);
    await adminPage.getByRole("button", { name: "Работа" }).click();
    await adminPage.getByRole("button", { name: "Возможности" }).click();
    await adminPage.getByRole("button", { name: "Каталог" }).click();
    const redemptionCard = adminPage.locator(".era-card", { hasText: "E2E Reward Redeemer" });
    await expect(redemptionCard).toBeVisible();
    await redemptionCard.getByPlaceholder("Ответ участнику").fill("Свяжемся с Вами по почте.");
    await redemptionCard.getByRole("button", { name: "Отправить ответ" }).click();
    await expect(redemptionCard.getByText("ответ отправлен")).toBeVisible();
    await redemptionCard.getByRole("button", { name: "Обменять и списать баллы" }).click();
    await expect(redemptionCard).toHaveCount(0);
  } finally {
    await adminContext.close();
    await participantContext.close();
  }
});