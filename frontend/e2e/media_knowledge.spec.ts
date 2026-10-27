import { expect, test } from "@playwright/test";

test("media knowledge supports real text creation, search, editing, pinning and reversible hiding", async ({ page }) => {
  const title = `Интервью ${Date.now()}`;
  await page.goto("/app/?devTelegramId=900003#/media");
  await page.getByRole("button", { name: /База знаний.*Инструкции, шаблоны/ }).click();
  await page.getByRole("button", { name: "Добавить материал в базу", exact: true }).click();
  await page.getByLabel("Название материала", { exact: true }).fill(title);
  await page.getByLabel("Категория материала", { exact: true }).selectOption("journalism");
  await page.getByLabel("Текст или описание", { exact: true }).fill("Начните с короткого вопроса.");
  await page.getByLabel("Закрепить в начале списка", { exact: true }).check();
  await page.getByRole("button", { name: "Сохранить материал", exact: true }).click();
  await expect(page.getByText(`Закреплено · ${title}`, { exact: true })).toBeVisible();
  await page.getByLabel("Поиск в базе знаний", { exact: true }).fill(title);
  await page.getByRole("button", { name: `Изменить: ${title}`, exact: true }).click();
  await page.getByLabel("Текст или описание", { exact: true }).fill("Уточните ответ и попросите пример.");
  await page.getByRole("button", { name: "Сохранить материал", exact: true }).click();
  await expect(page.getByText("Уточните ответ и попросите пример.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Скрыть материал", exact: true }).click();
  await expect(page.getByText(`Закреплено · ${title}`, { exact: true })).toHaveCount(0);
  await page.getByLabel("Показывать скрытые материалы", { exact: true }).check();
  await expect(page.getByText(`Закреплено · ${title} · скрыт`, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Вернуть в каталог", exact: true }).click();
  await expect(page.getByText(`Закреплено · ${title}`, { exact: true })).toBeVisible();
  for (const width of [320, 430, 768]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  }
});

test("media catalogue deep link opens the full knowledge screen", async ({ page }) => {
  await page.goto("/app/?devTelegramId=900003&eraPath=media%2Ffiles");
  await expect(page.getByRole("heading", { name: "База знаний" })).toBeVisible();
  await expect(page.getByLabel("Поиск в базе знаний", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/#\/media\/files$/);
});
