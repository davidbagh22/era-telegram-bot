import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;

async function enterAdminWorkspace(page: import("@playwright/test").Page) {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
  await page.getByRole("button", { name: "Профиль" }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await expect(page.getByText("Управление", { exact: true })).toBeVisible();
}

test("admin creates an office and assigns the seeded participant to it", async ({ page }) => {
  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: "Люди" }).click();
  await page.getByRole("button", { name: "Должности" }).click();

  const officeTitle = `E2E Office ${Date.now()}`;
  await page.getByPlaceholder("Название").fill(officeTitle);
  await page.getByRole("button", { name: "Добавить должность" }).click();
  await expect(page.getByText(officeTitle)).toBeVisible();

  const officeCard = page.locator(".era-card", { hasText: officeTitle });
  await officeCard.getByRole("button", { name: "Назначить человека" }).click();
  await officeCard.getByPlaceholder("Имя, username или Telegram ID").fill("E2E Participant");
  await officeCard.getByRole("button", { name: "Найти" }).click();
  await officeCard.getByRole("button", { name: "E2E Participant" }).click();
  await expect(officeCard.getByText(/Сейчас:.*E2E Participant/)).toBeVisible();
});