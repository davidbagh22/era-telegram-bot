import { expect, test } from "@playwright/test";

test("registered participant joins media once through the shared server membership", async ({ page }) => {
  await page.goto("/app/?devTelegramId=900001#/media");
  await page.getByRole("button", { name: "Присоединиться к медиаотделу", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Медиа", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Присоединиться к медиаотделу", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Управление медиа", exact: true })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Медиа", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Присоединиться к медиаотделу", exact: true })).toHaveCount(0);
});
