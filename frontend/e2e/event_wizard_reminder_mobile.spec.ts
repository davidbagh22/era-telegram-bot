import { expect, test } from "@playwright/test";

// Uses only the disposable CI admin fixture. Never publishes or sends reminders.
test("custom reminder input and action fit a 320px Telegram viewport", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/app/?devTelegramId=900003");
  await page.getByRole("navigation", { name: "Основная навигация" })
    .getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await page.getByRole("button", { name: /Мероприятие.*Создать и вести/ }).click();
  await page.getByRole("button", { name: /Создать мероприятие.*Черновик/ }).click();
  await page.getByRole("button", { name: "＋ Создать мероприятие" }).click();
  for (let step = 2; step <= 8; step += 1) {
    await page.getByRole("button", { name: "Продолжить" }).click();
    await expect(page.getByText(`ШАГ ${step} ИЗ 10`)).toBeVisible();
  }

  const input = page.getByPlaceholder("Например, 30");
  const add = page.getByRole("button", { name: "Добавить", exact: true });
  const [inputBox, addBox] = await Promise.all([input.boundingBox(), add.boundingBox()]);
  expect(inputBox).not.toBeNull();
  expect(addBox).not.toBeNull();
  if (!inputBox || !addBox) return;

  for (const box of [inputBox, addBox]) {
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(321);
  }
  expect(inputBox.width).toBeGreaterThan(70);
  expect(inputBox.x + inputBox.width).toBeLessThanOrEqual(addBox.x + 1);
  expect(Math.abs(inputBox.y - addBox.y)).toBeLessThanOrEqual(2);

  await input.fill("30");
  await add.click();
  await expect(page.getByText(/Сохранено:.*30 мин/)).toBeVisible();
});
