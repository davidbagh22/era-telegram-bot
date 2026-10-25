import { expect, test } from "@playwright/test";

test("media calendars keep KSOORS separate and require approval and a publication link", async ({ page }) => {
  const title = `КСООРС · репортаж ${Date.now()}`;
  await page.goto("/app/?devTelegramId=900003#/media");
  await page.getByRole("button", { name: /^КСООРС →/ }).click();
  await expect(page.getByRole("heading", { name: "Контент-план", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "+ Добавить материал", exact: true }).click();
  await page.getByLabel("Название", { exact: true }).fill(title);
  await page.getByLabel("Текст / замысел", { exact: true }).fill("Отчёт о работе команды");
  await page.getByLabel("Дата и время · Ереван", { exact: true }).fill("2026-11-01T19:00");
  await page.getByRole("button", { name: "Сохранить в календаре", exact: true }).click();
  await expect(page.getByText(title, { exact: true })).toBeVisible();
  await expect(page.getByText(/1 ноября.*19:00/)).toBeVisible();
  // The newly created calendar entry is the only interactive publication card.
  await page.getByRole("button", { name: "На согласование", exact: true }).click();
  await expect(page.getByText("На согласовании", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Утвердить", exact: true }).click();
  await expect(page.getByText("Готово", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Подтвердить публикацию по ссылке", exact: true })).toBeDisabled();
  await page.getByLabel("Ссылка на вышедший материал", { exact: true }).fill("https://t.me/ksoors_arm/123");
  await page.getByRole("button", { name: "Подтвердить публикацию по ссылке", exact: true }).click();
  await page.getByLabel("Показать", { exact: true }).selectOption("published");
  await expect(page.getByText(title, { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Открыть публикацию ↗", exact: true })).toHaveAttribute("href", "https://t.me/ksoors_arm/123");
  await page.getByRole("button", { name: "← Медиаотдел", exact: true }).click();
  await page.getByRole("button", { name: /^ЭРА →/ }).click();
  await expect(page.getByText(title, { exact: true })).toHaveCount(0);
});
