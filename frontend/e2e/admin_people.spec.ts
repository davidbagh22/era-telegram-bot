import { expect, test } from "@playwright/test";

const ADMIN_TELEGRAM_ID = 900003;

async function enterAdminWorkspace(page: import("@playwright/test").Page) {
  await page.goto(`/app/?devTelegramId=${ADMIN_TELEGRAM_ID}`);
  await page.getByRole("button", { name: "Профиль" }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await expect(page.getByText("Управление", { exact: true })).toBeVisible();
}

test("admin searches the people directory, opens a participant, and awards points", async ({
  page,
}) => {
  await enterAdminWorkspace(page);

  await page.getByRole("button", { name: "Люди" }).click();
  await page.getByRole("button", { name: "Участники" }).click();
  await page.getByPlaceholder("Имя, username или Telegram ID").fill("E2E Participant");

  await page.getByText("E2E Participant").click();
  await expect(page.getByText("Роль и доступ")).toBeVisible();
  await expect(page.getByText("Начислить или списать баллы")).toBeVisible();

  await page.getByPlaceholder("±баллы").fill("15");
  await page.getByPlaceholder("Причина").fill("E2E проверка начисления баллов");
  await page.getByRole("button", { name: "Применить" }).click();

  await expect(page.getByText("15 баллов")).toBeVisible();
});