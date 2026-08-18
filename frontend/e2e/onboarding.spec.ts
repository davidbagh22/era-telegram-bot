import { expect, test } from "@playwright/test";

// Community Verification ToR §71: approved user sees "Как устроена ЭРА" on
// first open, completing it never shows it again, and contextual help
// stays available afterwards.
const ONBOARDING_PENDING_TELEGRAM_ID = 900009;

test("approved user sees onboarding once, then lands straight on Home", async ({ page }) => {
  await page.goto(`/app/?devTelegramId=${ONBOARDING_PENDING_TELEGRAM_ID}`);

  await expect(page.getByRole("heading", { name: "Как устроена ЭРА" })).toBeVisible();
  // Sanity check on the actual copy, not just that some heading rendered.
  await expect(page.getByText("Главная", { exact: true })).toBeVisible();
  await expect(page.getByText("Личное пространство для фокуса и развития")).toBeVisible();

  await page.getByRole("button", { name: "Начать" }).click();

  // Lands on the real Home screen — same stable landmark pending_sync.spec.ts uses.
  await expect(page.getByText("УРОВЕНЬ", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Как устроена ЭРА" })).not.toBeVisible();

  // Reload: onboarding must not come back a second time for this user.
  await page.reload();
  await expect(page.getByText("УРОВЕНЬ", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Как устроена ЭРА" })).not.toBeVisible();

  // Contextual help stays available after onboarding (ToR §71 point 5) --
  // not a copy of the onboarding content, the existing "Что здесь?" mechanic.
  await expect(page.getByRole("button", { name: "Что здесь?" })).toBeVisible();
});
