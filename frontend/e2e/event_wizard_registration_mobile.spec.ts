import { expect, test } from "@playwright/test";

// Disposable CI admin fixture only: no event publication, registration or Telegram delivery.
test("registration deadline fits a 320px Telegram viewport", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/app/?devTelegramId=900003");
  await page.getByRole("navigation", { name: "Основная навигация" })
    .getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await page.getByRole("button", { name: /Мероприятие.*Создать и вести/ }).click();
  await page.getByRole("button", { name: /Создать мероприятие.*Черновик/ }).click();
  await page.getByRole("button", { name: "＋ Создать мероприятие" }).click();
  for (let step = 2; step <= 4; step += 1) {
    await page.getByRole("button", { name: "Продолжить" }).click();
    await expect(page.getByText(`ШАГ ${step} ИЗ 10`)).toBeVisible();
  }

  const registrationToggle = page.getByLabel("Регистрация нужна", { exact: true });
  if (!(await registrationToggle.isChecked())) await registrationToggle.check();
  const capacity = page.getByLabel("Количество мест", { exact: true });
  const deadline = page.getByLabel("Закрыть регистрацию", { exact: true });
  await capacity.fill("40");
  await deadline.fill("2026-11-19T17:30");
  await expect(capacity).toHaveValue("40");
  await expect(deadline).toHaveValue("2026-11-19T17:30");

  const [capacityBox, deadlineBox] = await Promise.all([capacity.boundingBox(), deadline.boundingBox()]);
  expect(capacityBox).not.toBeNull();
  expect(deadlineBox).not.toBeNull();
  if (!capacityBox || !deadlineBox) return;
  for (const box of [capacityBox, deadlineBox]) {
    expect(box.width).toBeGreaterThan(160);
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(321);
  }
  expect(capacityBox.y + capacityBox.height).toBeLessThanOrEqual(deadlineBox.y + 1);
});
