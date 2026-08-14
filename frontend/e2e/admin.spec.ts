import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;

async function enterAdminWorkspace(page: import("@playwright/test").Page) {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
  await expect(page.getByRole("button", { name: "Профиль" })).toBeVisible();
  await page.getByRole("button", { name: "Профиль" }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await expect(page.getByText("Управление", { exact: true })).toBeVisible();
}

test("admin enters separate management workspace and approves a pending applicant", async ({ page }) => {
  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: "Люди" }).click();
  await page.getByRole("button", { name: "Заявки" }).click();
  await expect(page.getByText("E2E Pending Applicant")).toBeVisible();
  await page.locator(".era-card", { hasText: "E2E Pending Applicant" }).getByRole("button", { name: "Одобрить" }).click();
  await expect(page.getByText("E2E Pending Applicant")).not.toBeVisible();
});

test("admin control has analytics system and maintenance as separate destinations", async ({ page }) => {
  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: "Контроль" }).click();
  await expect(page.getByRole("button", { name: /Аналитика/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Состояние системы/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Обслуживание/ })).toBeVisible();
});