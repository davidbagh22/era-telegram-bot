import { expect, test } from "@playwright/test";

const LEADER_TELEGRAM_ID = 900002;
const ADMIN_TELEGRAM_ID = 900003;
const ACTIVITY_TITLE = "E2E активность";
const SUBMITTER_NAME = "E2E Activity Submitter";

async function enterWorkspace(page: import("@playwright/test").Page, telegramId: number) {
  await page.goto(`/app/?devTelegramId=${telegramId}`);
  await page.getByRole("button", { name: "Профиль" }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
}

test("leader pre-approves an activity submission, then the admin does the final review", async ({ browser }) => {
  const leaderContext = await browser.newContext();
  const leaderPage = await leaderContext.newPage();
  const adminContext = await browser.newContext();
  const adminPage = await adminContext.newPage();

  try {
    await enterWorkspace(leaderPage, LEADER_TELEGRAM_ID);
    await expect(leaderPage.getByRole("heading", { name: "Пространство лидера" })).toBeVisible();
    await leaderPage.getByRole("button", { name: /Активности/ }).click();
    await expect(leaderPage.getByRole("heading", { name: "Активности" })).toBeVisible();

    const leaderCard = leaderPage.locator(".era-card", { hasText: ACTIVITY_TITLE });
    await expect(leaderCard).toBeVisible();
    await expect(leaderCard.getByText(SUBMITTER_NAME)).toBeVisible();
    await leaderCard.getByRole("button", { name: "✅ Принять" }).click();
    await expect(leaderPage.locator(".era-card", { hasText: ACTIVITY_TITLE })).toHaveCount(0);

    await enterWorkspace(adminPage, ADMIN_TELEGRAM_ID);
    await expect(adminPage.getByText("Управление", { exact: true })).toBeVisible();
    await adminPage.getByRole("button", { name: "Работа" }).click();
    await adminPage.getByRole("button", { name: /Мероприятия/ }).click();
    await adminPage.getByRole("button", { name: /Добавить активности/ }).click();
    await adminPage.getByRole("button", { name: /Проверить результаты/ }).click();

    const adminCard = adminPage.locator(".era-card", { hasText: ACTIVITY_TITLE });
    await expect(adminCard).toBeVisible();
    await expect(adminCard.getByText("проверено лидером")).toBeVisible();
    await adminCard.getByRole("button", { name: "✅ Принять и начислить" }).click();
    await expect(adminPage.locator(".era-card", { hasText: ACTIVITY_TITLE })).toHaveCount(0);
  } finally {
    await leaderContext.close().catch(() => undefined);
    await adminContext.close().catch(() => undefined);
  }
});
