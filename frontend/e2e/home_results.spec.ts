import { expect, test } from "@playwright/test";

test("cancelled projects, registrations and pending items are not presented as confirmed results", async ({ page }) => {
  await page.goto("/app/?devTelegramId=900019");
  await expect(page.getByRole("navigation", { name: "Основная навигация" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Открыть профиль" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Твоя орбита" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Ближайшее" })).toBeVisible();
  await expect(page.getByText(/Завершено проектов:|Подтверждено записей:|Подтверждено посещений:/)).toHaveCount(0);
  await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("button", { name: "Я", exact: true }).click();
  await expect(page.getByText("записей в обзоре", { exact: true })).toBeVisible();
  await expect(page.getByText("результатов", { exact: true })).toHaveCount(0);
});
