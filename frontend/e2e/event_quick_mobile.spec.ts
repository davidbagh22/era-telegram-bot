import { expect, test } from "@playwright/test";

test("quick event date and time fit a 320px Telegram viewport", async ({ page }) => {
  // CI-only admin fixture; create a disposable draft, never publish or send Telegram messages.
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/app/?devTelegramId=900003");
  await page.getByRole("navigation", { name: "Основная навигация" })
    .getByRole("button", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: /Управление ЭРА/ }).click();
  await page.getByRole("button", { name: /Мероприятие.*Создать и вести/ }).click();
  await page.getByRole("button", { name: /Создать мероприятие.*Черновик/ }).click();
  await page.getByRole("button", { name: /Быстро: текст и фото/ }).click();

  const dialog = page.getByRole("dialog", { name: "Быстрое создание" });
  await expect(dialog).toBeVisible();
  const date = dialog.getByLabel("Дата", { exact: true });
  const time = dialog.getByLabel("Время", { exact: true });
  await expect(date).toBeVisible();
  await expect(time).toBeVisible();
  await date.fill("2026-11-20");
  await time.fill("18:30");
  await expect(date).toHaveValue("2026-11-20");
  await expect(time).toHaveValue("18:30");

  const [outer, dateBox, timeBox] = await Promise.all([
    dialog.boundingBox(), date.boundingBox(), time.boundingBox(),
  ]);
  expect(outer).not.toBeNull();
  expect(dateBox).not.toBeNull();
  expect(timeBox).not.toBeNull();
  if (!outer || !dateBox || !timeBox) return;
  for (const box of [dateBox, timeBox]) {
    expect(box.x).toBeGreaterThanOrEqual(outer.x - 1);
    expect(box.x + box.width).toBeLessThanOrEqual(outer.x + outer.width + 1);
    expect(box.x + box.width).toBeLessThanOrEqual(321);
  }
  // Two native controls must stack, rather than overlap, on a narrow screen.
  expect(dateBox.y + dateBox.height).toBeLessThanOrEqual(timeBox.y + 1);
});
