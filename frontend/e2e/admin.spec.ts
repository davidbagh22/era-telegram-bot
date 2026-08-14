import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;

async function enterAdminWorkspace(page: import("@playwright/test").Page) {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
  await expect(page.getByRole("button", { name: "Профиль" })).toBeVisible();
  await expect(page.getByText("Управление", { exact: true })).not.toBeVisible();
  await page.getByRole("button", { name: "Профиль" }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await expect(page.getByText("Управление", { exact: true })).toBeVisible();
}

test("admin enters the separate management workspace and approves the seeded pending applicant", async ({ page }) => {
  await enterAdminWorkspace(page);

  await page.getByRole("button", { name: "Люди" }).click();
  await page.getByRole("button", { name: "Заявки" }).click();

  const applicantCard = page.getByText("E2E Pending Applicant");
  await expect(applicantCard).toBeVisible();

  await page
    .locator(".era-card", { hasText: "E2E Pending Applicant" })
    .getByRole("button", { name: "Одобрить" })
    .click();

  await expect(page.getByText("E2E Pending Applicant")).not.toBeVisible();
});

test("admin control is a dedicated section with analytics system and maintenance", async ({ page }) => {
  await enterAdminWorkspace(page);

  await page.getByRole("button", { name: "Контроль" }).click();
  await expect(page.getByRole("button", { name: /Аналитика/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Состояние системы/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Обслуживание/ })).toBeVisible();
});