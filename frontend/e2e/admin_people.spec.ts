import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;

async function enterAdminWorkspace(page: import("@playwright/test").Page) {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
  await page.getByRole("button", { name: "Профиль" }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await expect(page.getByText("Управление", { exact: true })).toBeVisible();
}

test("admin opens a rich participant profile and awards points", async ({ page }) => {
  await enterAdminWorkspace(page);
  await page.getByRole("button", { name: "Люди" }).click();
  await page.getByRole("button", { name: "Участники" }).click();
  await page.getByPlaceholder("Имя, username или Telegram ID").fill("E2E Participant");
  await page.getByText("E2E Participant").click();

  await expect(page.getByText("Карточка участника")).toBeVisible();
  await expect(page.getByText("Анкета при регистрации")).toBeVisible();
  await expect(page.getByText("Показатели участника")).toBeVisible();

  await page.getByRole("button", { name: "Управление", exact: true }).click();
  await expect(page.getByText("Роль и статус доступа")).toBeVisible();
  await expect(page.getByText("Баллы", { exact: true })).toBeVisible();

  await page.getByPlaceholder("± баллы").fill("15");
  await page.getByPlaceholder("Причина ручной корректировки").fill("E2E проверка начисления баллов");
  await page.getByRole("button", { name: "Применить вручную" }).click();

  await page.getByRole("button", { name: "Обзор", exact: true }).click();
  const balanceCard = page.getByText("Баллов сейчас").locator("..");
  await expect(balanceCard).toContainText("15");
});
